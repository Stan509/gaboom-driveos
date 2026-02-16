from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from agencies.models import ReservationRequest
from clients.models import ClientAccount
from core.models_platform import PlatformSettings
from core.views import _send_platform_email
from marketing.ai_engine import generate_message
from marketing.models import (
    AutomationRule, CampaignSend, CampaignVariant, MktCampaign, WhatsAppOutbox,
)


class Command(BaseCommand):
    help = "Process Marketing Engine 2.0 automations and send messages."

    def handle(self, *args, **options):
        now = timezone.now()
        processed = 0
        skipped = 0
        failed = 0

        rules = AutomationRule.objects.filter(enabled=True, dry_run=False).select_related("agency", "template")
        for rule in rules:
            agency = rule.agency
            clients = self._target_clients(rule, agency, now)
            if not clients:
                continue

            campaign, variant = self._get_campaign_variant(rule, agency)
            for client in clients:
                if self._already_sent(campaign, client, now):
                    skipped += 1
                    continue

                body = self._personalise(variant.body_text, client, agency)
                subject = variant.subject or f"{agency.name} — {campaign.name}"

                if campaign.channel_email and client.email:
                    ok = self._send_email(agency, client.email, subject, body)
                    if ok:
                        CampaignSend.objects.create(
                            campaign=campaign, variant=variant, client=client,
                            channel="email", meta={"automation_rule": rule.key},
                        )
                        processed += 1
                    else:
                        failed += 1

                if campaign.channel_whatsapp and getattr(client, "phone", ""):
                    ok = self._send_whatsapp(agency, client.phone, body)
                    status = "sent" if ok else "failed"
                    WhatsAppOutbox.objects.create(
                        agency=agency, campaign=campaign, client=client,
                        phone=client.phone, message=body, status=status,
                        sent_at=now if ok else None,
                    )
                    if ok:
                        CampaignSend.objects.create(
                            campaign=campaign, variant=variant, client=client,
                            channel="whatsapp", meta={"automation_rule": rule.key},
                        )
                        processed += 1
                    else:
                        failed += 1

            rule.last_run_at = now
            rule.save(update_fields=["last_run_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — {processed} sent, {skipped} skipped, {failed} failed."
            )
        )

    def _target_clients(self, rule, agency, now):
        delay_minutes = rule.delay_minutes or 0
        delay_days = rule.delay_days or 0
        cutoff = now - timedelta(minutes=delay_minutes)
        if rule.key == "reservation_pending_followup":
            qs = ReservationRequest.objects.filter(
                agency=agency,
                status="pending",
                created_at__lte=cutoff,
                client_account__isnull=False,
            ).values_list("client_account_id", flat=True)
            return list(ClientAccount.objects.filter(pk__in=qs))
        if rule.key == "booking_confirmed":
            qs = ReservationRequest.objects.filter(
                agency=agency,
                status__in=["confirmed", "contracted"],
                created_at__gte=rule.last_run_at or now - timedelta(days=7),
                client_account__isnull=False,
            ).values_list("client_account_id", flat=True)
            return list(ClientAccount.objects.filter(pk__in=qs))
        if rule.key == "pre_start_reminder":
            target_day = (now + timedelta(days=delay_days or 1)).date()
            qs = ReservationRequest.objects.filter(
                agency=agency,
                status__in=["confirmed", "contracted"],
                start_date=target_day,
                client_account__isnull=False,
            ).values_list("client_account_id", flat=True)
            return list(ClientAccount.objects.filter(pk__in=qs))
        if rule.key == "post_end_review":
            target_day = (now - timedelta(days=delay_days or 1)).date()
            qs = ReservationRequest.objects.filter(
                agency=agency,
                status__in=["confirmed", "contracted"],
                end_date=target_day,
                client_account__isnull=False,
            ).values_list("client_account_id", flat=True)
            return list(ClientAccount.objects.filter(pk__in=qs))
        if rule.key == "inactive_30d_offer":
            cutoff_day = (now - timedelta(days=30 + delay_days)).date()
            active_ids = ReservationRequest.objects.filter(
                agency=agency,
                created_at__gte=cutoff_day,
                client_account__isnull=False,
            ).values_list("client_account_id", flat=True)
            return list(ClientAccount.objects.filter(agency=agency).exclude(pk__in=active_ids))
        return []

    def _get_campaign_variant(self, rule, agency):
        objective_map = {
            "reservation_pending_followup": "relance",
            "booking_confirmed": "fidelisation",
            "pre_start_reminder": "relance",
            "post_end_review": "avis",
            "inactive_30d_offer": "promo",
        }
        objective = objective_map.get(rule.key, "promo")
        name = f"Auto — {rule.get_key_display()}"
        campaign, _ = MktCampaign.objects.get_or_create(
            agency=agency,
            name=name,
            defaults={
                "objective": objective,
                "channel_email": rule.channel in ("email", "both"),
                "channel_whatsapp": rule.channel in ("whatsapp", "both"),
                "status": "running",
            },
        )
        if campaign.objective != objective:
            campaign.objective = objective
        campaign.channel_email = rule.channel in ("email", "both")
        campaign.channel_whatsapp = rule.channel in ("whatsapp", "both")
        campaign.status = "running"
        campaign.save(update_fields=["objective", "channel_email", "channel_whatsapp", "status"])

        content = rule.custom_content or ""
        subject = ""
        if not content and rule.template:
            content = rule.template.content
            subject = rule.template.subject
        if not content:
            content = generate_message(objective=objective, style="simple", channel="email", agence=agency.name)
        variant, _ = CampaignVariant.objects.get_or_create(
            campaign=campaign,
            variant="A",
            defaults={"body_text": content, "subject": subject, "style": "simple"},
        )
        variant.body_text = content
        if subject:
            variant.subject = subject
        variant.style = variant.style or "simple"
        variant.save(update_fields=["body_text", "subject", "style"])
        return campaign, variant

    def _already_sent(self, campaign, client, now):
        cutoff = now - timedelta(days=1)
        return CampaignSend.objects.filter(
            campaign=campaign, client=client, sent_at__gte=cutoff,
        ).exists()

    def _send_email(self, agency, to_email, subject, body_text):
        api_key = agency.marketing_email_api_key
        if not api_key:
            return False
        ps = PlatformSettings.get()
        ps.smtp_provider = "brevo_api"
        ps.smtp_host = ""
        ps.smtp_from_email = (
            agency.marketing_email_from
            or agency.contact_email
            or ps.smtp_from_email
        )
        return _send_platform_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html="",
            template_key="mkt_automation",
            agency=agency,
            smtp_api_key_override=api_key,
            platform_settings=ps,
        )

    def _send_whatsapp(self, agency, phone, body):
        api_key = agency.marketing_whatsapp_api_key
        phone_id = agency.marketing_whatsapp_phone_id
        if not api_key or not phone_id:
            return False
        if api_key.lower().startswith("test"):
            return True
        clean_phone = "".join(c for c in phone if c.isdigit())
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {"body": body},
        }
        try:
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{phone_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=12,
            )
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    def _personalise(self, text, client, agency):
        replacements = {
            "{nom}": getattr(client, "full_name", str(client)),
            "{agence}": agency.name,
            "{ville}": getattr(agency, "city", "") or "",
        }
        for key, val in replacements.items():
            text = text.replace(key, str(val or ""))
        return text
