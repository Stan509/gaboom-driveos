"""
Dashboard views for growth features:
- Theme settings
- Marketing dashboard
- Promo codes CRUD
- Site banners CRUD
- Email campaigns CRUD
"""
from decimal import Decimal

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from agencies.models import (
    AgencyThemeSettings, MarketingCampaign, CampaignLog,
    CampaignAutomation, CampaignStep,
    PromoCode, SiteBanner, Vehicle,
)
from clients.models import ClientAccount
from core.permissions import has_perm, require_perm
from dashboard.ai_writer import (
    generate_message, rewrite_message,
    OBJECTIVES, STYLES, CHANNELS, VARIABLES,
)
from dashboard.services import compute_marketing_stats


def _agency(request):
    return request.user.agency



# ═══════════════════════════ THEME SETTINGS ══════════════════════════

@require_perm("settings.edit")
def theme_settings(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    ts, _ = AgencyThemeSettings.objects.get_or_create(agency=agency)

    if request.method == "POST" and has_perm(request.user, "settings.edit"):
        ts.theme_choice = request.POST.get("theme_choice", ts.theme_choice)
        ts.primary_color = request.POST.get("primary_color", "").strip()[:20]
        ts.secondary_color = request.POST.get("secondary_color", "").strip()[:20]
        try:
            ts.border_radius = int(request.POST.get("border_radius", 14))
        except (ValueError, TypeError):
            pass
        ts.enable_animations = request.POST.get("enable_animations") == "1"
        ts.enable_glow_effect = request.POST.get("enable_glow_effect") == "1"
        ts.save()
        messages.success(request, "Thème mis à jour.")
        return redirect("dashboard:theme_settings")

    return render(request, "dashboard/growth/themes.html", {
        "page_id": "themes", "breadcrumb": "Thèmes",
        "ts": ts,
        "theme_choices": AgencyThemeSettings.THEME_CHOICES,
    })


# ═══════════════════════════ MARKETING DASHBOARD ═════════════════════

@require_perm("marketing.view")
def marketing_dashboard(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    stats = compute_marketing_stats(agency)

    # Smart suggestions (Part 8)
    suggestions = []
    if stats["negotiation_rate"] > 40:
        suggestions.append({
            "type": "warning",
            "title": "Taux de négociation élevé",
            "message": f"{stats['negotiation_rate']}% des réservations incluent une négociation. Suggéré : activer le prix flexible.",
        })
    if stats["conversion_rate"] < 30 and stats["total_30"] > 5:
        suggestions.append({
            "type": "info",
            "title": "Conversion faible",
            "message": f"Seulement {stats['conversion_rate']}% de conversion. Suggéré : créer un code promo pour booster les réservations.",
        })
    if stats["repeat_customer_rate"] < 20 and stats["total_reservations"] > 10:
        suggestions.append({
            "type": "info",
            "title": "Fidélisation à améliorer",
            "message": f"Seulement {stats['repeat_customer_rate']}% de clients récurrents. Lancez une campagne email ciblée.",
        })

    return render(request, "dashboard/growth/marketing.html", {
        "page_id": "marketing", "breadcrumb": "Marketing",
        "stats": stats, "suggestions": suggestions,
    })


# ═══════════════════════════ PROMO CODES ═════════════════════════════

@require_perm("promotions.view")
def promo_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    promos = PromoCode.objects.filter(agency=agency)
    return render(request, "dashboard/growth/promos.html", {
        "page_id": "promotions", "breadcrumb": "Promotions",
        "promos": promos,
    })


@require_perm("promotions.edit")
def promo_create(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)

    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()[:50]
        ptype = request.POST.get("type", "percent")
        try:
            value = Decimal(request.POST.get("value", "0"))
        except Exception:
            value = Decimal("0")
        valid_until = request.POST.get("valid_until") or None
        try:
            max_usage = int(request.POST.get("max_usage", 0))
        except (ValueError, TypeError):
            max_usage = 0

        if not code:
            messages.error(request, "Le code est requis.")
            return redirect("dashboard:promo_create")
        if PromoCode.objects.filter(agency=agency, code=code).exists():
            messages.error(request, "Ce code existe déjà.")
            return redirect("dashboard:promo_create")

        PromoCode.objects.create(
            agency=agency, code=code, type=ptype, value=value,
            valid_until=valid_until, max_usage=max_usage,
        )
        messages.success(request, f"Code promo {code} créé.")
        return redirect("dashboard:promo_list")

    return render(request, "dashboard/growth/promo_form.html", {
        "page_id": "promotions", "breadcrumb": "Nouvelle promotion",
        "editing": False,
    })


@require_perm("promotions.edit")
def promo_edit(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    promo = get_object_or_404(PromoCode, pk=pk, agency=agency)

    if request.method == "POST":
        promo.code = request.POST.get("code", promo.code).strip().upper()[:50]
        promo.type = request.POST.get("type", promo.type)
        try:
            promo.value = Decimal(request.POST.get("value", str(promo.value)))
        except Exception:
            pass
        promo.valid_until = request.POST.get("valid_until") or None
        try:
            promo.max_usage = int(request.POST.get("max_usage", promo.max_usage))
        except (ValueError, TypeError):
            pass
        promo.active = request.POST.get("active") == "1"
        promo.save()
        messages.success(request, f"Code promo {promo.code} mis à jour.")
        return redirect("dashboard:promo_list")

    return render(request, "dashboard/growth/promo_form.html", {
        "page_id": "promotions", "breadcrumb": f"Modifier {promo.code}",
        "promo": promo, "editing": True,
    })


@require_perm("promotions.edit")
def promo_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    promo = get_object_or_404(PromoCode, pk=pk, agency=agency)
    promo.delete()
    messages.success(request, "Code promo supprimé.")
    return redirect("dashboard:promo_list")


# ═══════════════════════════ SITE BANNERS ════════════════════════════

@require_perm("promotions.view")
def banner_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    banners = SiteBanner.objects.filter(agency=agency)
    return render(request, "dashboard/growth/banners.html", {
        "page_id": "banners", "breadcrumb": "Bannières",
        "banners": banners,
    })


@require_perm("promotions.edit")
def banner_create(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)

    if request.method == "POST":
        banner = SiteBanner(agency=agency)
        _fill_banner(banner, request)
        banner.save()
        messages.success(request, "Bannière créée.")
        return redirect("dashboard:banner_list")

    return render(request, "dashboard/growth/banner_form.html", {
        "page_id": "banners", "breadcrumb": "Nouvelle bannière",
        "editing": False,
        "type_choices": SiteBanner.BANNER_TYPE_CHOICES,
        "device_choices": SiteBanner.DEVICE_CHOICES,
        "animation_choices": SiteBanner.ANIMATION_CHOICES,
    })


@require_perm("promotions.edit")
def banner_edit(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    banner = get_object_or_404(SiteBanner, pk=pk, agency=agency)

    if request.method == "POST":
        _fill_banner(banner, request)
        banner.save()
        messages.success(request, "Bannière mise à jour.")
        return redirect("dashboard:banner_list")

    return render(request, "dashboard/growth/banner_form.html", {
        "page_id": "banners", "breadcrumb": f"Modifier bannière #{pk}",
        "banner": banner, "editing": True,
        "type_choices": SiteBanner.BANNER_TYPE_CHOICES,
        "device_choices": SiteBanner.DEVICE_CHOICES,
        "animation_choices": SiteBanner.ANIMATION_CHOICES,
    })


@require_perm("promotions.edit")
def banner_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    banner = get_object_or_404(SiteBanner, pk=pk, agency=agency)
    banner.delete()
    messages.success(request, "Bannière supprimée.")
    return redirect("dashboard:banner_list")


def _fill_banner(banner, request):
    banner.type = request.POST.get("type", banner.type)
    banner.title = request.POST.get("title", "").strip()[:200]
    banner.subtitle = request.POST.get("subtitle", "").strip()[:300]
    banner.button_text = request.POST.get("button_text", "").strip()[:60]
    banner.button_link = request.POST.get("button_link", "").strip()[:500]
    banner.active = request.POST.get("active") == "1"
    try:
        banner.priority = int(request.POST.get("priority", 0))
    except (ValueError, TypeError):
        pass
    banner.start_date = request.POST.get("start_date") or None
    banner.end_date = request.POST.get("end_date") or None
    banner.target_device = request.POST.get("target_device", "all")
    banner.animation_type = request.POST.get("animation_type", "fade")
    if request.FILES.get("image"):
        banner.image = request.FILES["image"]


# ═══════════════════════════ EMAIL CAMPAIGNS ═════════════════════════

@require_perm("marketing.view")
def campaign_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    campaigns = MarketingCampaign.objects.filter(agency=agency)
    return render(request, "dashboard/growth/campaigns.html", {
        "page_id": "campaigns", "breadcrumb": "Campagnes",
        "campaigns": campaigns,
    })


def _campaign_ctx(request):
    """Shared context for campaign create/edit forms."""
    agency = _agency(request)
    return {
        "target_choices": MarketingCampaign.TARGET_CHOICES,
        "ai_objectives": OBJECTIVES,
        "ai_styles": STYLES,
        "ai_channels": CHANNELS,
        "ai_variables": VARIABLES,
        "trigger_choices": CampaignAutomation.TRIGGER_CHOICES,
        "vehicles": Vehicle.objects.filter(agency=agency),
        "agency_name": agency.name,
    }


def _save_campaign_extras(request, campaign):
    """Save channel_config and automation data from POST."""
    channel_email = request.POST.get("channel_email") == "on"
    channel_whatsapp = request.POST.get("channel_whatsapp") == "on"
    campaign.channel_config = {
        "email": channel_email,
        "whatsapp": channel_whatsapp,
        "whatsapp_mode": request.POST.get("whatsapp_mode", "standard"),
        "whatsapp_target": request.POST.get("whatsapp_target", "whatsapp_only"),
    }
    campaign.save(update_fields=["channel_config"])

    auto_enabled = request.POST.get("auto_enabled") == "on"
    is_sequence = request.POST.get("auto_mode") == "sequence"
    trigger = request.POST.get("auto_trigger", "manual")
    stop_conds = request.POST.getlist("stop_conditions")

    auto, _ = CampaignAutomation.objects.get_or_create(campaign=campaign)
    auto.enabled = auto_enabled
    auto.is_sequence = is_sequence
    auto.trigger = trigger
    auto.stop_conditions = stop_conds
    auto.save()

    if is_sequence and auto_enabled:
        auto.steps.all().delete()
        step_days = request.POST.getlist("step_day")
        step_channels = request.POST.getlist("step_channel")
        step_contents = request.POST.getlist("step_content")
        step_times = request.POST.getlist("step_time")
        for i, (d, ch, ct, tm) in enumerate(zip(step_days, step_channels, step_contents, step_times)):
            CampaignStep.objects.create(
                automation=auto, order=i, day_offset=int(d or 0),
                channel=ch or "email", content=ct or "",
                send_time=tm or "09:00",
            )


@require_perm("marketing.edit")
def campaign_create(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()[:200]
        content = request.POST.get("content", "").strip()
        target_type = request.POST.get("target_type", "all")
        scheduled_at = request.POST.get("scheduled_at") or None

        if not title:
            messages.error(request, "Le titre est requis.")
            return redirect("dashboard:campaign_create")

        status = "draft"
        if scheduled_at:
            status = "scheduled"

        campaign = MarketingCampaign.objects.create(
            agency=agency, title=title, content=content,
            target_type=target_type, scheduled_at=scheduled_at, status=status,
        )
        _save_campaign_extras(request, campaign)
        messages.success(request, "Campagne créée.")
        return redirect("dashboard:campaign_list")

    ctx = {"page_id": "campaigns", "breadcrumb": "Nouvelle campagne", "editing": False}
    ctx.update(_campaign_ctx(request))
    return render(request, "dashboard/growth/campaign_form.html", ctx)


@require_perm("marketing.edit")
def campaign_edit(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    campaign = get_object_or_404(MarketingCampaign, pk=pk, agency=agency)

    if request.method == "POST":
        campaign.title = request.POST.get("title", campaign.title).strip()[:200]
        campaign.content = request.POST.get("content", campaign.content).strip()
        campaign.target_type = request.POST.get("target_type", campaign.target_type)
        campaign.scheduled_at = request.POST.get("scheduled_at") or None
        if campaign.status == "draft" and campaign.scheduled_at:
            campaign.status = "scheduled"
        campaign.save()
        _save_campaign_extras(request, campaign)
        messages.success(request, "Campagne mise à jour.")
        return redirect("dashboard:campaign_list")

    ctx = {
        "page_id": "campaigns", "breadcrumb": "Modifier campagne",
        "campaign": campaign, "editing": True,
    }
    ctx.update(_campaign_ctx(request))
    return render(request, "dashboard/growth/campaign_form.html", ctx)


@require_perm("marketing.edit")
def campaign_send(request: HttpRequest, pk: int) -> HttpResponse:
    """Send campaign emails via SMTP."""
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    campaign = get_object_or_404(MarketingCampaign, pk=pk, agency=agency)

    if campaign.status == "sent":
        messages.error(request, "Campagne déjà envoyée.")
        return redirect("dashboard:campaign_list")

    # Get target clients
    clients_qs = ClientAccount.objects.filter(agency=agency, is_active=True)
    if campaign.target_type == "inactive":
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=60)
        active_ids = (
            agency.reservation_requests.filter(created_at__gte=cutoff, client_account__isnull=False)
            .values_list("client_account_id", flat=True).distinct()
        )
        clients_qs = clients_qs.exclude(pk__in=active_ids)
    elif campaign.target_type == "frequent":
        from django.db.models import Count
        frequent_ids = (
            agency.reservation_requests.filter(client_account__isnull=False)
            .values("client_account").annotate(cnt=Count("pk"))
            .filter(cnt__gte=3).values_list("client_account", flat=True)
        )
        clients_qs = clients_qs.filter(pk__in=frequent_ids)
    elif campaign.target_type == "negotiators":
        nego_ids = (
            agency.reservation_requests.exclude(negotiation_status="none")
            .filter(client_account__isnull=False)
            .values_list("client_account_id", flat=True).distinct()
        )
        clients_qs = clients_qs.filter(pk__in=nego_ids)

    sent_count = 0
    failed_count = 0
    for client in clients_qs:
        try:
            from django.core.mail import send_mail
            from django.conf import settings as django_settings
            send_mail(
                subject=campaign.title,
                message=campaign.content,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[client.email],
                fail_silently=False,
            )
            CampaignLog.objects.create(campaign=campaign, client=client, status="sent")
            sent_count += 1
        except Exception:
            CampaignLog.objects.create(campaign=campaign, client=client, status="failed")
            failed_count += 1

    campaign.status = "sent"
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["status", "sent_at"])

    messages.success(request, f"Campagne envoyée : {sent_count} envoyés, {failed_count} échoués.")
    return redirect("dashboard:campaign_list")


@require_perm("marketing.edit")
def campaign_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    campaign = get_object_or_404(MarketingCampaign, pk=pk, agency=agency)
    campaign.delete()
    messages.success(request, "Campagne supprimée.")
    return redirect("dashboard:campaign_list")


# ═══════════════════════════ AI WRITER API ══════════════════════════════

@require_perm("marketing.edit")
def api_ai_writer(request: HttpRequest) -> JsonResponse:
    """Generate or rewrite marketing content (offline, template-based)."""
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
        return JsonResponse({"ok": True, "text": text})

    elif action == "rewrite":
        mode = data.get("mode", "improve")
        text = data.get("text", "")
        if not text:
            return JsonResponse({"error": "No text to rewrite"}, status=400)
        result = rewrite_message(mode, text, emojis=data.get("emojis", True))
        return JsonResponse({"ok": True, "text": result})

    return JsonResponse({"error": "Unknown action"}, status=400)
