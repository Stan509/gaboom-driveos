"""
Management command: process_campaign_steps

Scans CampaignAutomation records with enabled sequences and creates
OutboundMessage entries for steps whose day_offset has been reached.

Usage:
    python manage.py process_campaign_steps
    # Run periodically via cron / Task Scheduler
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from agencies.models import (
    CampaignAutomation, OutboundMessage,
)
from clients.models import ClientAccount


class Command(BaseCommand):
    help = "Process automation campaign steps and queue outbound messages."

    def handle(self, *args, **options):
        now = timezone.now()
        processed = 0
        skipped = 0

        automations = (
            CampaignAutomation.objects
            .filter(enabled=True, is_sequence=True)
            .select_related("campaign", "campaign__agency")
            .prefetch_related("steps")
        )

        for auto in automations:
            campaign = auto.campaign
            if campaign.status not in ("sent", "scheduled", "draft"):
                continue

            agency = campaign.agency
            start_date = auto.created_at

            # Determine target clients
            clients = self._get_target_clients(campaign, agency)
            if not clients:
                continue

            for step in auto.steps.all():
                step_due = start_date + timedelta(days=step.day_offset)
                if now < step_due:
                    continue

                for client in clients:
                    # Check stop conditions
                    if self._should_stop(auto, client):
                        skipped += 1
                        continue

                    # Avoid duplicate messages
                    exists = OutboundMessage.objects.filter(
                        campaign=campaign, step=step, client=client,
                    ).exists()
                    if exists:
                        continue

                    content = self._personalise(step.content or campaign.content, client, agency)

                    OutboundMessage.objects.create(
                        campaign=campaign,
                        step=step,
                        client=client,
                        channel=step.channel,
                        content=content,
                        status="queued",
                        scheduled_at=step_due.replace(
                            hour=step.send_time.hour,
                            minute=step.send_time.minute,
                            second=0,
                        ),
                    )
                    processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — {processed} message(s) queued, {skipped} skipped (stop conditions)."
            )
        )

    # ── helpers ──────────────────────────────────────────────

    def _get_target_clients(self, campaign, agency):
        qs = ClientAccount.objects.filter(agency=agency)
        target = campaign.target_type
        if target == "active":
            qs = qs.filter(contracts__status="active").distinct()
        elif target == "inactive":
            qs = qs.exclude(contracts__status="active").distinct()
        elif target == "negotiators":
            qs = qs.filter(reservations__status="negotiating").distinct()
        return list(qs)

    def _should_stop(self, auto, client):
        """Check stop conditions stored in automation.stop_conditions."""
        conds = auto.stop_conditions or []
        if not conds:
            return False

        if "reservation_created" in conds:
            if hasattr(client, "reservations") and client.reservations.exists():
                return True
        if "contract_signed" in conds:
            if hasattr(client, "contracts") and client.contracts.filter(status="active").exists():
                return True
        if "client_replied" in conds:
            # Placeholder — would check inbound messages when implemented
            pass
        return False

    def _personalise(self, text, client, agency):
        """Replace template variables with client/agency data."""
        replacements = {
            "{nom}": getattr(client, "full_name", str(client)),
            "{agence}": agency.name,
            "{ville}": getattr(agency, "city", ""),
        }
        for key, val in replacements.items():
            text = text.replace(key, str(val or ""))
        return text
