"""
Dashboard views for Marketing Engine 2.0:
- Campaigns CRUD with A/B test
- Automations management
- Analytics dashboard
- WhatsApp outbox
- AI writer API
- Click tracking
"""
import json
import urllib.parse
from datetime import timedelta

import requests
from django.contrib import messages
from django.db import models
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from agencies.models import Vehicle
from clients.models import ClientAccount
from core.models_platform import PlatformSettings
from core.permissions import require_perm
from core.views import _send_platform_email
from marketing.models import (
    MktCampaign, CampaignVariant, CampaignSend, MarketingTemplate,
    AutomationRule, WhatsAppOutbox,
)
from marketing.ai_engine import (
    generate_message, rewrite_message, score_message, OBJECTIVES, STYLES, CHANNELS, VARIABLES,
)
from marketing import bandit


# ═══════════════════════════ HELPERS ══════════════════════════════════

def _agency(request):
    return request.user.agency


def _send_marketing_email_to(agency, to_email, subject, body_text, body_html=""):
    api_key = agency.marketing_email_api_key
    if not api_key:
        return False, "missing"
    ps = PlatformSettings.get()
    ps.smtp_provider = "brevo_api"
    ps.smtp_host = ""
    ps.smtp_from_email = (
        agency.marketing_email_from
        or agency.contact_email
        or ps.smtp_from_email
    )
    ok = _send_platform_email(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        template_key="mkt_campaign",
        agency=agency,
        smtp_api_key_override=api_key,
        platform_settings=ps,
    )
    return ok, ""


def _send_whatsapp_message(agency, phone, body):
    api_key = agency.marketing_whatsapp_api_key
    phone_id = agency.marketing_whatsapp_phone_id
    if not api_key or not phone_id:
        return False, "missing"
    if api_key.lower().startswith("test"):
        return True, ""
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
        if resp.status_code >= 200 and resp.status_code < 300:
            return True, ""
        return False, resp.text[:300]
    except Exception as exc:
        return False, str(exc)



# ═══════════════════════════ CAMPAIGNS LIST ═══════════════════════════

@require_perm("marketing.view")
def campaign_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    campaigns = MktCampaign.objects.filter(agency=agency).annotate(
        send_count=Count("sends"),
        click_count=Count("sends", filter=Q(sends__clicked_at__isnull=False)),
        conv_count=Count("sends", filter=Q(sends__converted_at__isnull=False)),
    )

    # KPIs
    total_sends = sum(c.send_count for c in campaigns)
    total_clicks = sum(c.click_count for c in campaigns)
    total_convs = sum(c.conv_count for c in campaigns)
    click_rate = round(total_clicks / total_sends * 100, 1) if total_sends else 0

    return render(request, "dashboard/marketing/campaign_list.html", {
        "page_id": "mkt_campaigns",
        "breadcrumb": "Campagnes",
        "campaigns": campaigns,
        "kpi_sends": total_sends,
        "kpi_clicks": total_clicks,
        "kpi_convs": total_convs,
        "kpi_click_rate": click_rate,
        "email_key_set": bool(agency.marketing_email_api_key_encrypted),
        "whatsapp_key_set": bool(agency.marketing_whatsapp_api_key_encrypted),
        "whatsapp_phone_id": agency.marketing_whatsapp_phone_id,
        "marketing_email_from": agency.marketing_email_from,
    })


@require_perm("marketing.edit")
@require_POST
def marketing_settings_update(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    email_from = request.POST.get("marketing_email_from", "").strip()
    wa_phone_id = request.POST.get("marketing_whatsapp_phone_id", "").strip()
    email_key = request.POST.get("marketing_email_api_key", "").strip()
    wa_key = request.POST.get("marketing_whatsapp_api_key", "").strip()

    update_fields = []
    agency.marketing_email_from = email_from
    update_fields.append("marketing_email_from")
    agency.marketing_whatsapp_phone_id = wa_phone_id
    update_fields.append("marketing_whatsapp_phone_id")
    if email_key:
        agency.set_marketing_email_api_key(email_key)
        update_fields.append("marketing_email_api_key_encrypted")
    if wa_key:
        agency.set_marketing_whatsapp_api_key(wa_key)
        update_fields.append("marketing_whatsapp_api_key_encrypted")
    agency.save(update_fields=update_fields)
    messages.success(request, _("Clés API marketing enregistrées."))
    return redirect("dashboard:mkt_campaign_list")


# ═══════════════════════════ CAMPAIGN CREATE ══════════════════════════

def _campaign_ctx(request):
    """Shared context for campaign create/edit forms."""
    agency = _agency(request)
    return {
        "ai_objectives": OBJECTIVES,
        "ai_styles": STYLES,
        "ai_channels": CHANNELS,
        "ai_variables": VARIABLES,
        "vehicles": Vehicle.objects.filter(agency=agency),
        "agency_name": agency.name,
        "agency_slug": agency.slug,
    }


@require_perm("marketing.edit")
def campaign_create(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()[:200]
        if not name:
            messages.error(request, _("Le nom est requis."))
            return redirect("dashboard:mkt_campaign_create")

        objective = request.POST.get("objective", "promo")
        channel_email = request.POST.get("channel_email") == "on"
        channel_whatsapp = request.POST.get("channel_whatsapp") == "on"
        target = request.POST.get("target", "all_clients")
        scheduled_at = request.POST.get("scheduled_at") or None
        ab_enabled = request.POST.get("ab_enabled") == "on"

        status = "scheduled" if scheduled_at else "draft"

        campaign = MktCampaign.objects.create(
            agency=agency, name=name, objective=objective,
            channel_email=channel_email, channel_whatsapp=channel_whatsapp,
            target=target, scheduled_at=scheduled_at, status=status,
            ab_enabled=ab_enabled,
        )

        # Variant A
        body_a = request.POST.get("body_a", "").strip()
        subject_a = request.POST.get("subject_a", "").strip()
        style_a = request.POST.get("style_a", "simple")
        score_a = score_message(body_a)["total"] if body_a else 0
        CampaignVariant.objects.create(
            campaign=campaign, variant="A",
            subject=subject_a, body_text=body_a,
            style=style_a, score=score_a,
        )

        # Variant B (if A/B enabled)
        if ab_enabled:
            body_b = request.POST.get("body_b", "").strip()
            subject_b = request.POST.get("subject_b", "").strip()
            style_b = request.POST.get("style_b", "simple")
            score_b = score_message(body_b)["total"] if body_b else 0
            CampaignVariant.objects.create(
                campaign=campaign, variant="B",
                subject=subject_b, body_text=body_b,
                style=style_b, score=score_b,
            )

        messages.success(request, _("Campagne créée."))
        return redirect("dashboard:mkt_campaign_list")

    ctx = {"page_id": "mkt_campaigns", "breadcrumb": _("Nouvelle campagne"), "editing": False}
    ctx.update(_campaign_ctx(request))
    return render(request, "dashboard/marketing/campaign_form.html", ctx)


# ═══════════════════════════ CAMPAIGN EDIT ════════════════════════════

@require_perm("marketing.edit")
def campaign_edit(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    campaign = get_object_or_404(MktCampaign, pk=pk, agency=agency)

    if request.method == "POST":
        campaign.name = request.POST.get("name", campaign.name).strip()[:200]
        campaign.objective = request.POST.get("objective", campaign.objective)
        campaign.channel_email = request.POST.get("channel_email") == "on"
        campaign.channel_whatsapp = request.POST.get("channel_whatsapp") == "on"
        campaign.target = request.POST.get("target", campaign.target)
        campaign.scheduled_at = request.POST.get("scheduled_at") or None
        campaign.ab_enabled = request.POST.get("ab_enabled") == "on"
        if campaign.status == "draft" and campaign.scheduled_at:
            campaign.status = "scheduled"
        campaign.save()

        # Update variant A
        var_a, _ = CampaignVariant.objects.get_or_create(campaign=campaign, variant="A")
        var_a.body_text = request.POST.get("body_a", var_a.body_text).strip()
        var_a.subject = request.POST.get("subject_a", var_a.subject).strip()
        var_a.style = request.POST.get("style_a", var_a.style)
        var_a.score = score_message(var_a.body_text)["total"] if var_a.body_text else 0
        var_a.save()

        # Update variant B
        if campaign.ab_enabled:
            var_b, _ = CampaignVariant.objects.get_or_create(campaign=campaign, variant="B")
            var_b.body_text = request.POST.get("body_b", var_b.body_text).strip()
            var_b.subject = request.POST.get("subject_b", var_b.subject).strip()
            var_b.style = request.POST.get("style_b", var_b.style)
            var_b.score = score_message(var_b.body_text)["total"] if var_b.body_text else 0
            var_b.save()

        messages.success(request, _("Campagne mise à jour."))
        return redirect("dashboard:mkt_campaign_list")

    variant_a = campaign.variants.filter(variant="A").first()
    variant_b = campaign.variants.filter(variant="B").first()

    ctx = {
        "page_id": "mkt_campaigns", "breadcrumb": _("Modifier campagne"),
        "campaign": campaign, "editing": True,
        "variant_a": variant_a, "variant_b": variant_b,
    }
    ctx.update(_campaign_ctx(request))
    return render(request, "dashboard/marketing/campaign_form.html", ctx)


# ═══════════════════════════ CAMPAIGN DELETE ══════════════════════════

@require_perm("marketing.edit")
@require_POST
def campaign_delete(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    campaign = get_object_or_404(MktCampaign, pk=pk, agency=agency)
    campaign.delete()
    messages.success(request, _("Campagne supprimée."))
    return redirect("dashboard:mkt_campaign_list")


# ═══════════════════════════ CAMPAIGN SEND ════════════════════════════

@require_perm("marketing.edit")
@require_POST
def campaign_send(request: HttpRequest, pk: int) -> HttpResponse:
    """Send campaign to target clients — creates CampaignSend + WhatsApp outbox."""
    agency = _agency(request)
    campaign = get_object_or_404(MktCampaign, pk=pk, agency=agency)

    clients = _get_target_clients(campaign, agency)
    variants = list(campaign.variants.filter(is_active=True))
    if not variants:
        messages.error(request, _("Aucune variante active."))
        return redirect("dashboard:mkt_campaign_list")
    if campaign.channel_email and not agency.marketing_email_api_key:
        messages.error(request, _("Ajoutez une clé API Email avant d'envoyer."))
        return redirect("dashboard:mkt_campaign_list")
    if campaign.channel_whatsapp and (
        not agency.marketing_whatsapp_api_key
        or not agency.marketing_whatsapp_phone_id
    ):
        messages.error(request, _("Ajoutez la clé API WhatsApp et le Phone ID avant d'envoyer."))
        return redirect("dashboard:mkt_campaign_list")

    sent_count = 0
    wa_count = 0
    email_fail = 0
    wa_fail = 0

    for i, client in enumerate(clients):
        # A/B split
        if campaign.ab_enabled and len(variants) > 1:
            variant = variants[i % len(variants)]
        else:
            variant = variants[0]

        # Build arm key for bandit
        arm_key = f"{campaign.objective}_{variant.style}_{variant.variant}"

        # Email send
        if campaign.channel_email and client.email:
            body = _personalise(variant.body_text, client, agency)
            subject = variant.subject or f"{agency.name} — {campaign.name}"
            ok, _ = _send_marketing_email_to(
                agency,
                client.email,
                subject,
                body,
            )
            if not ok:
                email_fail += 1
                continue
            CampaignSend.objects.create(
                campaign=campaign, variant=variant, client=client,
                channel="email",
                meta={"arm_key": arm_key},
            )
            bandit.record_pull(agency, arm_key)
            sent_count += 1

        # WhatsApp outbox
        if campaign.channel_whatsapp:
            phone = getattr(client, "phone", "") or ""
            if phone:
                body = _personalise(variant.body_text, client, agency)
                wa_link = f"https://wa.me/{_clean_phone(phone)}?text={urllib.parse.quote(body)}"
                ok, err = _send_whatsapp_message(agency, phone, body)
                status = "sent" if ok else "failed"
                WhatsAppOutbox.objects.create(
                    agency=agency, campaign=campaign, client=client,
                    phone=phone, message=body, wa_link=wa_link, status=status,
                    sent_at=timezone.now() if ok else None,
                )
                if ok:
                    CampaignSend.objects.create(
                        campaign=campaign, variant=variant, client=client,
                        channel="whatsapp",
                        meta={"arm_key": arm_key, "wa_link": wa_link},
                    )
                    bandit.record_pull(agency, arm_key)
                    wa_count += 1
                else:
                    wa_fail += 1

    campaign.status = "running"
    campaign.save(update_fields=["status"])

    label_emails_sent = _("email(s) envoyé(s)")
    label_wa_sent = _("WhatsApp envoyés")
    label_emails_failed = _("email(s) échoués")
    label_wa_failed = _("WhatsApp échoués")

    parts = [f"{sent_count} {label_emails_sent}"]
    if wa_count:
        parts.append(f"{wa_count} {label_wa_sent}")
    msg = ", ".join(parts)
    if email_fail or wa_fail:
        msg += f" - {email_fail} {label_emails_failed}, {wa_fail} {label_wa_failed}"
    messages.success(request, msg)
    return redirect("dashboard:mkt_campaign_list")


# ═══════════════════════════ AUTOMATIONS ══════════════════════════════

@require_perm("marketing.view")
def automation_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    rules = AutomationRule.objects.filter(agency=agency).annotate(
        fires_count=Count("id"),
        sends_count=Count("id"),
    )
    templates = MarketingTemplate.objects.filter(
        models.Q(agency=agency) | models.Q(agency__isnull=True)
    )

    return render(request, "dashboard/marketing/automations.html", {
        "page_id": "mkt_automations",
        "breadcrumb": "Automatisations",
        "rules": rules,
        "trigger_choices": AutomationRule.KEY_CHOICES,
        "channel_choices": AutomationRule.CHANNEL_CHOICES,
        "templates": templates,
    })


@require_perm("marketing.edit")
@require_POST
def automation_create(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    name = request.POST.get("name", "").strip()[:120]
    trigger = request.POST.get("trigger", "reservation_pending_followup")
    channel = request.POST.get("channel", "email")
    delay_hours = int(request.POST.get("delay_hours", 0) or 0)
    template_pk = request.POST.get("template", "")
    message_body = request.POST.get("message_body", "").strip()
    enabled = request.POST.get("enabled") == "on"
    dry_run = request.POST.get("dry_run") == "on"

    template_obj = None
    if template_pk:
        template_obj = MarketingTemplate.objects.filter(pk=template_pk).first()

    rule = AutomationRule.objects.create(
        agency=agency,
        name=name,
        key=trigger,
        enabled=enabled,
        dry_run=dry_run,
        channel=channel,
        delay_minutes=delay_hours * 60,
        template=template_obj,
        template_key=str(template_pk),
        custom_content=message_body,
    )
    messages.success(request, _("Règle '%(rule)s' créée.") % {'rule': name or rule.get_key_display()})
    return redirect("dashboard:mkt_automations")


@require_perm("marketing.edit")
@require_POST
def automation_delete(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    rule = get_object_or_404(AutomationRule, pk=pk, agency=agency)
    rule.delete()
    messages.success(request, _("Règle supprimée."))
    return redirect("dashboard:mkt_automations")


@require_perm("marketing.edit")
@require_POST
def automation_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    rule = get_object_or_404(AutomationRule, pk=pk, agency=agency)
    val = request.POST.get("enabled", "")
    rule.enabled = val == "1"
    rule.save(update_fields=["enabled"])
    messages.success(request, _("Règle %(status)s.") % {'status': _('activée') if rule.enabled else _('désactivée')})
    return redirect("dashboard:mkt_automations")


@require_perm("marketing.edit")
@require_POST
def automation_update(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    rule = get_object_or_404(AutomationRule, pk=pk, agency=agency)
    rule.channel = request.POST.get("channel", rule.channel)
    rule.delay_minutes = int(request.POST.get("delay_minutes", rule.delay_minutes) or 0)
    rule.delay_days = int(request.POST.get("delay_days", rule.delay_days) or 0)
    rule.template_key = request.POST.get("template_key", rule.template_key)
    rule.custom_content = request.POST.get("custom_content", rule.custom_content)
    rule.save()
    messages.success(request, _("Règle mise à jour."))
    return redirect("dashboard:mkt_automations")


@require_perm("marketing.view")
def automation_dryrun(request: HttpRequest, pk: int) -> JsonResponse:
    """Generate a sample message for an automation rule (dry-run)."""
    agency = _agency(request)
    rule = get_object_or_404(AutomationRule, pk=pk, agency=agency)
    content = rule.custom_content or ""
    if not content:
        # Generate from template
        obj_map = {
            "reservation_pending_followup": "relance",
            "booking_confirmed": "fidelisation",
            "pre_start_reminder": "relance",
            "post_end_review": "avis",
            "inactive_30d_offer": "fidelisation",
        }
        objective = obj_map.get(rule.key, "relance")
        channel = "whatsapp" if rule.channel == "whatsapp" else "email"
        content = generate_message(
            objective=objective, style="simple", channel=channel,
            agence=agency.name,
        )
    sample = content.replace("{nom}", "Jean Dupont").replace("{agence}", agency.name)
    sample = sample.replace("{ville}", agency.city or "votre ville")
    return JsonResponse({"ok": True, "message": sample})


# ═══════════════════════════ ANALYTICS ════════════════════════════════

@require_perm("marketing.view")
def analytics(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    now = timezone.now()
    period = int(request.GET.get("period", 7))
    if period not in (7, 30):
        period = 7
    cutoff = now - timedelta(days=period)
    prev_cutoff = cutoff - timedelta(days=period)

    sends_all = CampaignSend.objects.filter(campaign__agency=agency)
    sends_period = sends_all.filter(sent_at__gte=cutoff)
    sends_prev = sends_all.filter(sent_at__gte=prev_cutoff, sent_at__lt=cutoff)

    def _count(qs, field=None):
        if field:
            return qs.filter(**{f"{field}__isnull": False}).count()
        return qs.count()

    total_sends = _count(sends_period)
    total_clicks = _count(sends_period, "clicked_at")
    total_convs = _count(sends_period, "converted_at")
    prev_sends = _count(sends_prev)
    prev_clicks = _count(sends_prev, "clicked_at")

    def _delta(cur, prev):
        if not prev:
            return 0
        return round((cur - prev) / prev * 100)

    kpi = {
        "campaigns": MktCampaign.objects.filter(agency=agency, status__in=["running", "scheduled"]).count(),
        "sends": total_sends,
        "clicks": total_clicks,
        "conversions": total_convs,
        "click_rate": round(total_clicks / total_sends * 100, 1) if total_sends else 0,
        "conv_rate": round(total_convs / total_sends * 100, 1) if total_sends else 0,
        "sends_delta": _delta(total_sends, prev_sends),
        "clicks_delta": _delta(total_clicks, prev_clicks),
    }

    # Daily bar chart data
    def _chart_data(qs, field=None):
        data = []
        max_val = 1
        for i in range(period):
            day = (now - timedelta(days=period - 1 - i)).date()
            if field:
                count = qs.filter(sent_at__date=day, **{f"{field}__isnull": False}).count()
            else:
                count = qs.filter(sent_at__date=day).count()
            data.append({"label": day.strftime("%d/%m"), "count": count})
            if count > max_val:
                max_val = count
        for d in data:
            d["pct"] = round(d["count"] / max_val * 100) if max_val else 0
        return data

    chart_sends = _chart_data(sends_all)
    chart_clicks = _chart_data(sends_all, "clicked_at")

    # Top campaigns by clicks
    top_campaigns = (
        MktCampaign.objects.filter(agency=agency)
        .annotate(click_count=Count("sends", filter=Q(sends__clicked_at__isnull=False)))
        .order_by("-click_count")[:5]
    )

    # Top templates
    top_templates = (
        MarketingTemplate.objects.filter(
            models.Q(agency=agency) | models.Q(agency__isnull=True)
        )
        .annotate(used_count=Count("id"))
        .order_by("-used_count")[:5]
    )

    # Conversion funnel
    funnel = [
        {"label": "Envois", "count": total_sends, "rate": None},
        {"label": "Clics", "count": total_clicks, "rate": kpi["click_rate"]},
        {"label": "Conversions", "count": total_convs, "rate": kpi["conv_rate"]},
    ]

    return render(request, "dashboard/marketing/analytics.html", {
        "page_id": "mkt_analytics",
        "breadcrumb": "Analytics Marketing",
        "period": period,
        "kpi": kpi,
        "chart_sends": chart_sends,
        "chart_clicks": chart_clicks,
        "top_campaigns": top_campaigns,
        "top_templates": top_templates,
        "funnel": funnel,
    })


# ═══════════════════════════ WHATSAPP OUTBOX ══════════════════════════

@require_perm("marketing.view")
def wa_outbox(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    filter_status = request.GET.get("status", "").strip()
    qs = WhatsAppOutbox.objects.filter(agency=agency).select_related("campaign", "client")
    if filter_status in ("pending", "sent", "failed"):
        qs = qs.filter(status=filter_status)

    all_qs = WhatsAppOutbox.objects.filter(agency=agency)

    return render(request, "dashboard/marketing/wa_outbox.html", {
        "page_id": "mkt_wa_outbox",
        "breadcrumb": "WhatsApp Outbox",
        "wa_messages": qs[:100],
        "filter_status": filter_status,
        "kpi_total": all_qs.count(),
        "kpi_pending": all_qs.filter(status="pending").count(),
        "kpi_sent": all_qs.filter(status="sent").count(),
        "kpi_failed": all_qs.filter(status="failed").count(),
    })


@require_perm("marketing.edit")
@require_POST
def wa_mark_sent(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    item = get_object_or_404(WhatsAppOutbox, pk=pk, agency=agency)
    item.status = "sent"
    item.sent_at = timezone.now()
    item.save(update_fields=["status", "sent_at"])
    return JsonResponse({"ok": True})


# ═══════════════════════════ AI WRITER API ════════════════════════════

@require_perm("marketing.edit")
def api_ai_writer(request: HttpRequest) -> JsonResponse:
    """Generate, rewrite, or score marketing content (offline)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action = data.get("action", "generate")
    agency = _agency(request)

    if action == "generate":
        text = generate_message(
            objective=data.get("objective", "promo"),
            style=data.get("style", "simple"),
            channel=data.get("channel", "email"),
            offre=data.get("offre", ""),
            voiture=data.get("voiture", ""),
            cta_link=data.get("cta_link", ""),
            agence=agency.name,
            emojis=data.get("emojis", True),
        )
        result = score_message(text)
        return JsonResponse({"ok": True, "text": text, "score": result})

    elif action == "rewrite":
        mode = data.get("mode", "improve")
        text = data.get("text", "")
        if not text:
            return JsonResponse({"error": "No text to rewrite"}, status=400)
        result_text = rewrite_message(mode, text, emojis=data.get("emojis", True))
        result = score_message(result_text)
        return JsonResponse({"ok": True, "text": result_text, "score": result})

    elif action == "score":
        text = data.get("text", "")
        if not text:
            return JsonResponse({"error": "No text to score"}, status=400)
        result = score_message(text)
        return JsonResponse({"ok": True, "score": result})

    return JsonResponse({"error": "Unknown action"}, status=400)


# ═══════════════════════════ CLICK TRACKING ═══════════════════════════

def track_click(request: HttpRequest, token: str) -> HttpResponse:
    """Public route: /t/<token>/ — records click and redirects."""
    from django.http import HttpResponseRedirect
    import uuid as _uuid

    try:
        token_uuid = _uuid.UUID(token)
    except ValueError:
        from django.http import Http404
        raise Http404

    send = get_object_or_404(CampaignSend, token=token_uuid)

    if not send.clicked_at:
        send.clicked_at = timezone.now()
        send.save(update_fields=["clicked_at"])

    # Get redirect URL from meta
    redirect_url = send.meta.get("redirect_url", "")
    if not redirect_url:
        # Fallback: agency public site
        if send.campaign and send.campaign.agency:
            redirect_url = f"/a/{send.campaign.agency.slug}/"
        else:
            redirect_url = "/"

    return HttpResponseRedirect(redirect_url)


# ═══════════════════════════ CONVERSION HOOK ══════════════════════════

def record_conversion_from_reservation(reservation):
    """
    Called when a reservation is confirmed.
    Checks if the reservation came from a campaign link (utm_campaign token).
    """
    # Check if reservation has a tracking token in source or meta
    token = getattr(reservation, "utm_token", None)
    if not token:
        return

    try:
        import uuid as _uuid
        token_uuid = _uuid.UUID(str(token))
        send = CampaignSend.objects.filter(token=token_uuid).first()
        if send and not send.converted_at:
            send.converted_at = timezone.now()
            send.save(update_fields=["converted_at"])

            # Record bandit reward
            arm_key = send.meta.get("arm_key", "")
            if arm_key and send.campaign:
                bandit.record_reward(send.campaign.agency, arm_key, converted=True)
    except (ValueError, Exception):
        pass


# ═══════════════════════════ HELPERS ══════════════════════════════════

def _get_target_clients(campaign, agency):
    qs = ClientAccount.objects.filter(agency=agency)
    target = campaign.target
    if target == "active_clients":
        qs = qs.filter(contracts__status="active").distinct()
    elif target == "inactive_30d":
        cutoff = timezone.now() - timedelta(days=30)
        qs = qs.exclude(contracts__created_at__gte=cutoff).distinct()
    return list(qs)


def _personalise(text, client, agency):
    replacements = {
        "{nom}": getattr(client, "full_name", str(client)),
        "{agence}": agency.name,
        "{ville}": getattr(agency, "city", "") or "",
    }
    for key, val in replacements.items():
        text = text.replace(key, str(val or ""))
    return text


def _clean_phone(phone):
    """Clean phone number for wa.me link."""
    return "".join(c for c in phone if c.isdigit() or c == "+")
