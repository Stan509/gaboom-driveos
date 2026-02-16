import json
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from agencies.models import Agency, Vehicle
from agencies.models_access import AgencyAccess, PaymentProof
from agencies.services import (
    dismiss_admin_alert, grant_bonus_days, renew_access,
    suspend_access,
)
from billing.models import Contract
from core.crypto import ensure_fernet_key, is_fernet_configured
from core.decorators import require_superadmin
from core.models_admin_alert import AdminAlert
from core.models_paypal_event import PayPalEvent
from core.models_platform import PlatformSettings, EmailTemplate, EmailSendLog
from core.views import _send_platform_email
from core.services_paypal_api import create_plan, test_oauth_token, test_plan
from core.services_platform import get_paypal_config

from .forms_platform import PlatformSettingsForm, EmailTemplateForm
from .models import AuditLog


def _log(action, request, agency=None, proof=None, note=""):
    AuditLog.objects.create(
        action=action,
        agency=agency,
        proof=proof,
        by_user=request.user,
        note=note,
    )


# ═══════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def overview(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    soon = now + timedelta(hours=48)

    all_access = AgencyAccess.objects.select_related("agency").all()
    kpi_total = all_access.count()
    kpi_trial = all_access.filter(status="trial").count()
    kpi_active = all_access.filter(status="active").count()
    kpi_suspended = all_access.filter(status="suspended").count()
    kpi_pending = PaymentProof.objects.filter(status="pending").count()
    kpi_expiring = all_access.filter(
        status__in=("trial", "active"),
        access_ends_at__lte=soon,
        access_ends_at__gt=now,
    ).count()
    kpi_paypal_alerts = all_access.filter(needs_admin_attention=True).count()
    kpi_paypal_active = all_access.filter(billing_mode="paypal", paypal_status="active").count()

    # Sparkline data: agencies created per day (last 30 days)
    thirty_ago = now - timedelta(days=30)
    from django.db.models.functions import TruncDate
    daily_counts = (
        Agency.objects.filter(created_at__gte=thirty_ago)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    spark_map = {r["day"]: r["count"] for r in daily_counts}
    spark_data = []
    for i in range(30):
        d = (thirty_ago + timedelta(days=i)).date()
        spark_data.append({"date": d, "count": spark_map.get(d, 0)})
    spark_max = max((s["count"] for s in spark_data), default=1) or 1

    # Urgent lists
    expiring_soon = (
        all_access.filter(
            status__in=("trial", "active"),
            access_ends_at__lte=soon,
            access_ends_at__gt=now,
        ).order_by("access_ends_at")[:10]
    )
    pending_proofs = (
        PaymentProof.objects.filter(status="pending")
        .select_related("access__agency", "uploaded_by")
        .order_by("uploaded_at")[:10]
    )

    # PayPal cancelled (switched to manual)
    paypal_cancelled = (
        all_access.filter(
            admin_alert_code__in=("paypal_to_manual", "paypal_cancelled"),
            needs_admin_attention=True,
        ).order_by("-billing_last_changed_at")[:10]
    )

    # Recent webhook events
    recent_webhooks = PayPalEvent.objects.all()[:8]

    # Admin alerts count (dedicated table)
    kpi_admin_alerts = AdminAlert.objects.filter(is_read=False).count()

    return render(request, "superadmin/overview.html", {
        "page_id": "overview",
        "kpi_total": kpi_total, "kpi_trial": kpi_trial,
        "kpi_active": kpi_active, "kpi_suspended": kpi_suspended,
        "kpi_pending": kpi_pending, "kpi_expiring": kpi_expiring,
        "kpi_paypal_alerts": kpi_paypal_alerts, "kpi_paypal_active": kpi_paypal_active,
        "kpi_admin_alerts": kpi_admin_alerts,
        "spark_data": spark_data, "spark_max": spark_max,
        "expiring_soon": expiring_soon,
        "pending_proofs": pending_proofs,
        "paypal_cancelled": paypal_cancelled,
        "recent_webhooks": recent_webhooks,
    })


# ═══════════════════════════════════════════════════════════════════════
# AGENCIES LIST
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def agencies_list(request: HttpRequest) -> HttpResponse:
    qs = AgencyAccess.objects.select_related("agency").all()

    # Filters
    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    pending_only = request.GET.get("pending", "")
    alerts_only = request.GET.get("alerts", "")
    billing_filter = request.GET.get("billing", "")
    sort = request.GET.get("sort", "recent")

    if search:
        qs = qs.filter(
            Q(agency__name__icontains=search)
            | Q(agency__users__email__icontains=search)
        ).distinct()
    if status_filter:
        qs = qs.filter(status=status_filter)
    if pending_only:
        qs = qs.filter(proofs__status="pending").distinct()
    if alerts_only:
        qs = qs.filter(needs_admin_attention=True)
    if billing_filter:
        qs = qs.filter(billing_mode=billing_filter)

    if sort == "expiring":
        qs = qs.order_by("access_ends_at")
    elif sort == "name":
        qs = qs.order_by("agency__name")
    elif sort == "most_vehicles":
        qs = qs.annotate(vc=Count("agency__vehicles")).order_by("-vc")
    else:  # recent
        qs = qs.order_by("-created_at")

    rows = []
    for acc in qs[:200]:
        owner = acc.agency.users.filter(role="agency_owner").first()
        pending_count = acc.proofs.filter(status="pending").count()
        rows.append({
            "access": acc,
            "owner_email": owner.email if owner else "—",
            "pending_count": pending_count,
        })

    return render(request, "superadmin/agencies.html", {
        "page_id": "agencies",
        "rows": rows,
        "search": search, "status_filter": status_filter,
        "pending_only": pending_only, "alerts_only": alerts_only,
        "billing_filter": billing_filter, "sort": sort,
    })


# ═══════════════════════════════════════════════════════════════════════
# AGENCY DETAIL
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def agency_detail(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_object_or_404(AgencyAccess.objects.select_related("agency"), pk=pk)
    agency = access.agency
    owner = agency.users.filter(role="agency_owner").first()
    proofs = PaymentProof.objects.filter(access=access).order_by("-uploaded_at")
    logs = AuditLog.objects.filter(agency=agency).order_by("-created_at")[:30]

    vehicle_count = Vehicle.objects.filter(agency=agency).count()
    contract_count = Contract.objects.filter(agency=agency).count()
    user_count = agency.users.count()

    tab = request.GET.get("tab", "access")

    return render(request, "superadmin/agency_detail.html", {
        "page_id": "agencies",
        "access": access, "agency": agency, "owner": owner,
        "proofs": proofs, "logs": logs, "tab": tab,
        "vehicle_count": vehicle_count,
        "contract_count": contract_count,
        "user_count": user_count,
    })


# ═══════════════════════════════════════════════════════════════════════
# PROOFS LIST
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def proofs_list(request: HttpRequest) -> HttpResponse:
    qs = (
        PaymentProof.objects
        .select_related("access__agency", "uploaded_by", "reviewed_by")
        .order_by(
            # pending first, then by uploaded_at desc
            models_case_order(),
            "-uploaded_at",
        )
    )

    status_filter = request.GET.get("status", "")
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, "superadmin/proofs.html", {
        "page_id": "proofs",
        "proofs": qs[:200],
        "status_filter": status_filter,
    })


def models_case_order():
    from django.db.models import Case, IntegerField, Value, When
    return Case(
        When(status="pending", then=Value(0)),
        When(status="rejected", then=Value(1)),
        When(status="approved", then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )


# ═══════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def saas_settings(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        messages.success(request, "Paramètres enregistrés.")
        _log("SETTINGS_UPDATE", request, note="Paramètres SaaS mis à jour")
        return redirect("superadmin:settings")

    return render(request, "superadmin/settings.html", {
        "page_id": "settings",
        "trial_days": 3,
        "renew_days": 30,
        "bonus_days": 7,
    })


# ═══════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def audit_list(request: HttpRequest) -> HttpResponse:
    qs = AuditLog.objects.select_related("agency", "by_user").order_by("-created_at")

    action_filter = request.GET.get("action", "")
    if action_filter:
        qs = qs.filter(action=action_filter)

    return render(request, "superadmin/audit.html", {
        "page_id": "audit",
        "logs": qs[:300],
        "action_filter": action_filter,
        "action_choices": AuditLog.ACTION_CHOICES,
    })


# ═══════════════════════════════════════════════════════════════════════
# ACTIONS (POST only)
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def action_renew(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    renew_access(access, by_user=request.user)
    _log("ACCESS_RENEW", request, agency=access.agency,
         note=f"Renouvelé 30j → {access.access_ends_at:%d/%m/%Y %H:%M}")
    messages.success(request, f"{access.agency.name} renouvelé jusqu'au {access.access_ends_at:%d/%m/%Y %H:%M}.")
    return redirect(request.POST.get("next", "/saas/agencies/"))


@require_superadmin
def action_suspend(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    reason = request.POST.get("reason", "").strip()[:500] or "Suspension manuelle"
    suspend_access(access, reason=reason, by_user=request.user)
    _log("ACCESS_SUSPEND", request, agency=access.agency, note=reason)
    messages.success(request, f"{access.agency.name} suspendu.")
    return redirect(request.POST.get("next", "/saas/agencies/"))


@require_superadmin
def action_bonus(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    days = int(request.POST.get("days", 7))
    grant_bonus_days(access, days=days, by_user=request.user)
    _log("ACCESS_BONUS", request, agency=access.agency,
         note=f"+{days}j bonus → {access.access_ends_at:%d/%m/%Y %H:%M}")
    messages.success(request, f"+{days} jours bonus pour {access.agency.name}.")
    return redirect(request.POST.get("next", "/saas/agencies/"))


@require_superadmin
def action_save_notes(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    access.notes_internal = request.POST.get("notes_internal", "")
    access.save(update_fields=["notes_internal", "updated_at"])
    _log("NOTES_UPDATE", request, agency=access.agency, note="Notes internes mises à jour")
    messages.success(request, "Notes enregistrées.")
    return redirect(request.POST.get("next", f"/saas/agencies/{pk}/?tab=notes"))


@require_superadmin
@transaction.atomic
def action_proof_approve(request: HttpRequest, proof_pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    proof = get_object_or_404(PaymentProof.objects.select_related("access__agency"), pk=proof_pk)
    proof.status = "approved"
    proof.reviewed_by = request.user
    proof.reviewed_at = timezone.now()
    proof.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    renew_access(proof.access, by_user=request.user)
    _log("PROOF_APPROVE", request, agency=proof.access.agency, proof=proof,
         note=f"Preuve #{proof.pk} approuvée → renouvellement 30j")
    messages.success(request, f"Preuve #{proof.pk} approuvée — accès renouvelé 30j.")
    return redirect(request.POST.get("next", "/saas/proofs/"))


@require_superadmin
@transaction.atomic
def action_proof_reject(request: HttpRequest, proof_pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    proof = get_object_or_404(PaymentProof.objects.select_related("access__agency"), pk=proof_pk)
    note = request.POST.get("review_note", "").strip()
    if not note:
        messages.error(request, "Une raison est requise pour rejeter une preuve.")
        return redirect(request.POST.get("next", "/saas/proofs/"))
    proof.status = "rejected"
    proof.reviewed_by = request.user
    proof.reviewed_at = timezone.now()
    proof.review_note = note
    proof.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    _log("PROOF_REJECT", request, agency=proof.access.agency, proof=proof,
         note=f"Preuve #{proof.pk} rejetée: {note}")
    messages.success(request, f"Preuve #{proof.pk} rejetée.")
    return redirect(request.POST.get("next", "/saas/proofs/"))


@require_superadmin
def action_dismiss_alert(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    dismiss_admin_alert(access)
    _log("ALERT_DISMISS", request, agency=access.agency,
         note=f"Alerte traitée: {access.admin_alert_code}")
    messages.success(request, f"Alerte pour {access.agency.name} marquée comme traitée.")
    return redirect(request.POST.get("next", f"/saas/agencies/{pk}/"))


# ═══════════════════════════════════════════════════════════════════════
# PAYMENTS SETTINGS (PayPal + Domain)
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def payments_settings(request: HttpRequest) -> HttpResponse:
    ps = PlatformSettings.get()
    fernet_ok = is_fernet_configured()

    if request.method == "POST":
        action = request.POST.get("action", "save_settings")
        if action == "save_template":
            template_id = request.POST.get("template_id") or ""
            template = EmailTemplate.objects.filter(pk=template_id).first() if template_id else None
            template_form = EmailTemplateForm(request.POST, instance=template)
            if template_form.is_valid():
                template_form.save()
                messages.success(request, "Template email enregistré.")
            else:
                messages.error(request, "Template invalide.")
            return redirect("superadmin:payments_settings")
        if action == "delete_template":
            template_id = request.POST.get("template_id") or ""
            if template_id:
                EmailTemplate.objects.filter(pk=template_id).delete()
                messages.success(request, "Template supprimé.")
            return redirect("superadmin:payments_settings")
        form = PlatformSettingsForm(request.POST, instance=ps)
        if form.is_valid():
            form.save()
            _log("SETTINGS_UPDATE", request, note="Paramètres PayPal / domaine mis à jour")
            messages.success(request, "Configuration enregistrée.")
            return redirect("superadmin:payments_settings")
    else:
        form = PlatformSettingsForm(instance=ps)

    return render(request, "superadmin/payments_settings.html", {
        "page_id": "payments",
        "form": form,
        "fernet_ok": fernet_ok,
        "ps": ps,
        "email_templates": EmailTemplate.objects.all(),
        "email_logs": EmailSendLog.objects.select_related("agency").all()[:20],
    })


@require_superadmin
def payments_test_email(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    ps = PlatformSettings.get()
    form = PlatformSettingsForm(request.POST, instance=ps)
    if not form.is_valid():
        messages.error(request, "Formulaire invalide.")
        return redirect("superadmin:payments_settings")
    smtp_key = form.cleaned_data.get("smtp_api_key", "").strip()
    smtp_password = form.cleaned_data.get("smtp_password", "").strip()
    if not request.user.email:
        messages.error(request, "Adresse email superadmin manquante.")
        return redirect("superadmin:payments_settings")
    ps.smtp_provider = form.cleaned_data.get("smtp_provider") or ps.smtp_provider
    ps.smtp_host = form.cleaned_data.get("smtp_host") or ps.smtp_host
    ps.smtp_port = form.cleaned_data.get("smtp_port") or ps.smtp_port
    ps.smtp_username = form.cleaned_data.get("smtp_username") or ps.smtp_username
    ps.smtp_use_tls = form.cleaned_data.get("smtp_use_tls") if "smtp_use_tls" in form.cleaned_data else ps.smtp_use_tls
    ps.smtp_use_ssl = form.cleaned_data.get("smtp_use_ssl") if "smtp_use_ssl" in form.cleaned_data else ps.smtp_use_ssl
    ps.smtp_from_email = form.cleaned_data.get("smtp_from_email") or ps.smtp_from_email
    ps.smtp_reply_to = form.cleaned_data.get("smtp_reply_to") or ps.smtp_reply_to
    ok = _send_platform_email(
        to_email=request.user.email,
        subject="Gaboom DriveOS — Test email",
        body_text="Email de test envoyé depuis le dashboard superadmin.",
        template_key="test_email",
        smtp_password_override=smtp_password,
        smtp_api_key_override=smtp_key,
        platform_settings=ps,
    )
    if ok:
        _log("EMAIL_TEST", request, note=f"Test email envoyé à {request.user.email}")
        messages.success(request, f"Email de test envoyé à {request.user.email}.")
    else:
        messages.error(request, "Erreur envoi email. Vérifie les paramètres SMTP.")
    return redirect("superadmin:payments_settings")


# ═══════════════════════════════════════════════════════════════════════
# WEBHOOKS LOG
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def webhooks_log(request: HttpRequest) -> HttpResponse:
    qs = PayPalEvent.objects.all()

    search = request.GET.get("q", "").strip()
    event_filter = request.GET.get("type", "")
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")

    if search:
        qs = qs.filter(
            Q(subscription_id__icontains=search)
            | Q(agency_name__icontains=search)
            | Q(event_id__icontains=search)
        )
    if event_filter:
        qs = qs.filter(event_type=event_filter)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Distinct event types for filter dropdown
    event_types = (
        PayPalEvent.objects.values_list("event_type", flat=True)
        .distinct()
        .order_by("event_type")
    )

    return render(request, "superadmin/webhooks_log.html", {
        "page_id": "webhooks",
        "events": qs[:300],
        "search": search,
        "event_filter": event_filter,
        "date_from": date_from,
        "date_to": date_to,
        "event_types": event_types,
    })


# ═══════════════════════════════════════════════════════════════════════
# SETUP WIZARD
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def setup_wizard(request: HttpRequest) -> HttpResponse:
    """Main wizard page — 5-step stepper."""
    ps = PlatformSettings.get()
    cfg = get_paypal_config()
    fernet_ok = is_fernet_configured()
    has_secret = bool(ps.paypal_client_secret_encrypted)
    recent_events = PayPalEvent.objects.all()[:10]
    has_events = PayPalEvent.objects.exists()
    is_debug = django_settings.DEBUG

    return render(request, "superadmin/setup_wizard.html", {
        "page_id": "setup",
        "ps": ps,
        "cfg": cfg,
        "fernet_ok": fernet_ok,
        "has_secret": has_secret,
        "recent_events": recent_events,
        "has_events": has_events,
        "is_debug": is_debug,
    })


@require_superadmin
def setup_save_domain(request: HttpRequest) -> JsonResponse:
    """AJAX: save public_base_url."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST
    url = (data.get("public_base_url") or "").strip().rstrip("/")
    ps = PlatformSettings.get()
    ps.public_base_url = url
    ps.save(update_fields=["public_base_url", "updated_at"])
    _log("SETTINGS_UPDATE", request, note=f"Domaine mis à jour: {url}")
    return JsonResponse({"ok": True, "message": "Domaine enregistré.", "url": url})


@require_superadmin
def setup_save_keys(request: HttpRequest) -> JsonResponse:
    """AJAX: save PayPal mode + client_id + secret (per-mode fields)."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    ps = PlatformSettings.get()
    mode = data.get("paypal_mode", "sandbox")
    client_id = (data.get("paypal_client_id") or "").strip()
    secret = (data.get("paypal_client_secret") or "").strip()
    enable_auto = data.get("enable_paypal_auto", False)

    ps.paypal_mode = mode
    ps.enable_paypal_auto = bool(enable_auto)
    fields = ["paypal_mode", "enable_paypal_auto", "updated_at"]

    # Save client_id to the correct per-mode field
    if mode == "live":
        ps.paypal_client_id_live = client_id
        fields.append("paypal_client_id_live")
    else:
        ps.paypal_client_id_sandbox = client_id
        fields.append("paypal_client_id_sandbox")

    fernet_generated = False
    if secret:
        if not is_fernet_configured():
            ensure_fernet_key()
            fernet_generated = True
        ps.set_secret(mode, secret)
        if mode == "live":
            fields.append("paypal_client_secret_live_encrypted")
        else:
            fields.append("paypal_client_secret_sandbox_encrypted")

    ps.save(update_fields=fields)
    _log("SETTINGS_UPDATE", request, note=f"Clés PayPal ({mode}) mises à jour")
    msg = f"Clés PayPal ({mode}) enregistrées."
    if fernet_generated:
        msg += " FERNET_KEY générée automatiquement et sauvegardée dans .env."
    if secret:
        msg += " Secret chiffré enregistré."
    return JsonResponse({"ok": True, "message": msg})


@require_superadmin
def setup_save_plans(request: HttpRequest) -> JsonResponse:
    """AJAX: save plan IDs for all 3 plans (starter/business/enterprise)."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    ps = PlatformSettings.get()
    
    # Sandbox plans
    ps.paypal_plan_id_starter_sandbox = (data.get("paypal_plan_id_starter_sandbox") or "").strip()
    ps.paypal_plan_id_business_sandbox = (data.get("paypal_plan_id_business_sandbox") or "").strip()
    ps.paypal_plan_id_enterprise_sandbox = (data.get("paypal_plan_id_enterprise_sandbox") or "").strip()
    
    # Live plans
    ps.paypal_plan_id_starter_live = (data.get("paypal_plan_id_starter_live") or "").strip()
    ps.paypal_plan_id_business_live = (data.get("paypal_plan_id_business_live") or "").strip()
    ps.paypal_plan_id_enterprise_live = (data.get("paypal_plan_id_enterprise_live") or "").strip()
    
    # Legacy compatibility (keep existing fields)
    ps.paypal_plan_id_sandbox = ps.paypal_plan_id_business_sandbox  # Default to business
    ps.paypal_plan_id_live = ps.paypal_plan_id_business_live
    
    fields = [
        "paypal_plan_id_starter_sandbox", "paypal_plan_id_business_sandbox", "paypal_plan_id_enterprise_sandbox",
        "paypal_plan_id_starter_live", "paypal_plan_id_business_live", "paypal_plan_id_enterprise_live",
        "paypal_plan_id_sandbox", "paypal_plan_id_live", "updated_at"
    ]
    
    ps.save(update_fields=fields)
    _log("SETTINGS_UPDATE", request, note="Plan IDs PayPal (3 plans) mis à jour")
    return JsonResponse({"ok": True, "message": "Plan IDs des 3 plans enregistrés."})


@require_superadmin
def setup_save_webhook(request: HttpRequest) -> JsonResponse:
    """AJAX: save webhook settings."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    ps = PlatformSettings.get()
    wh_id = (data.get("paypal_webhook_id") or "").strip()
    ps.paypal_webhook_verify = bool(data.get("paypal_webhook_verify"))
    fields = ["paypal_webhook_verify", "updated_at"]
    # Save to per-mode field
    if ps.paypal_mode == "live":
        ps.paypal_webhook_id_live = wh_id
        fields.append("paypal_webhook_id_live")
    else:
        ps.paypal_webhook_id_sandbox = wh_id
        fields.append("paypal_webhook_id_sandbox")
    ps.save(update_fields=fields)
    _log("SETTINGS_UPDATE", request, note="Webhook PayPal mis à jour")
    return JsonResponse({"ok": True, "message": "Configuration webhook enregistrée."})


@require_superadmin
def setup_test_token(request: HttpRequest) -> JsonResponse:
    """AJAX: test PayPal OAuth token."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    result = test_oauth_token()
    return JsonResponse({"ok": result["ok"], "message": result["message"]})


@require_superadmin
def setup_test_plan(request: HttpRequest) -> JsonResponse:
    """AJAX: validate PayPal plan ID."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST
    plan_id = (data.get("plan_id") or "").strip()
    result = test_plan(plan_id=plan_id)
    return JsonResponse({"ok": result["ok"], "message": result["message"]})


@require_superadmin
def setup_create_plan(request: HttpRequest) -> JsonResponse:
    """AJAX: create a PayPal billing plan via API."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    price = (data.get("price") or "").strip()
    currency = (data.get("currency") or "USD").strip().upper()
    if not price:
        return JsonResponse({"ok": False, "message": "Prix requis."})

    result = create_plan(price=price, currency=currency)
    if result["ok"] and result["plan_id"]:
        # Auto-save plan_id + product_id to current mode's fields
        ps = PlatformSettings.get()
        fields = ["updated_at"]
        if ps.paypal_mode == "live":
            ps.paypal_plan_id_live = result["plan_id"]
            fields.append("paypal_plan_id_live")
            if result.get("product_id"):
                ps.paypal_product_id_live = result["product_id"]
                fields.append("paypal_product_id_live")
        else:
            ps.paypal_plan_id_sandbox = result["plan_id"]
            fields.append("paypal_plan_id_sandbox")
            if result.get("product_id"):
                ps.paypal_product_id_sandbox = result["product_id"]
                fields.append("paypal_product_id_sandbox")
        ps.save(update_fields=fields)
        _log("SETTINGS_UPDATE", request, note=f"Plan PayPal créé: {result['plan_id']}")

    return JsonResponse({
        "ok": result["ok"],
        "message": result["message"],
        "plan_id": result.get("plan_id", ""),
        "product_id": result.get("product_id", ""),
    })


@require_superadmin
def setup_test_webhook(request: HttpRequest) -> JsonResponse:
    """AJAX: test webhook endpoint reachability."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)

    cfg = get_paypal_config()
    if not cfg["base_url"]:
        return JsonResponse({"ok": False, "message": "URL publique non configurée."})

    webhook_url = cfg["webhook_url"]
    is_local = "localhost" in cfg["base_url"] or "127.0.0.1" in cfg["base_url"]

    if is_local:
        return JsonResponse({
            "ok": True,
            "message": f"Mode local détecté. Webhook URL: {webhook_url} — "
                       "utilisez 'Simuler événement' pour tester.",
        })

    return JsonResponse({
        "ok": True,
        "message": f"Webhook URL configurée: {webhook_url} — "
                   "collez cette URL dans votre dashboard PayPal.",
    })


@require_superadmin
def setup_simulate_webhook(request: HttpRequest) -> JsonResponse:
    """AJAX: insert a mock PayPalEvent (DEBUG only)."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)

    if not django_settings.DEBUG:
        return JsonResponse({
            "ok": False,
            "message": "Simulation disponible uniquement en mode DEBUG.",
        })

    mock_payload = {
        "id": "EVT-MOCK-" + timezone.now().strftime("%Y%m%d%H%M%S"),
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {
            "id": "I-MOCK123",
            "status": "ACTIVE",
            "plan_id": "P-MOCK456",
        },
        "create_time": timezone.now().isoformat(),
    }

    PayPalEvent.objects.create(
        event_id=mock_payload["id"],
        event_type=mock_payload["event_type"],
        resource_id="I-MOCK123",
        subscription_id="I-MOCK123",
        agency_name="[SIMULATION]",
        payload=mock_payload,
        processed=False,
        verified=False,
        note="Événement simulé depuis le Setup Wizard",
    )

    return JsonResponse({
        "ok": True,
        "message": "Événement simulé créé (BILLING.SUBSCRIPTION.ACTIVATED).",
    })


@require_superadmin
def setup_validate_all(request: HttpRequest) -> JsonResponse:
    """AJAX: validate all PayPal setup steps."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "POST requis."}, status=405)

    ps = PlatformSettings.get()
    cfg = get_paypal_config()
    
    # Step 1: Domain validation
    domain_ok = bool(ps.public_base_url and ps.public_base_url.strip())
    
    # Step 2: Keys validation
    if ps.paypal_mode == "live":
        keys_ok = bool(ps.paypal_client_id_live and ps.paypal_client_secret_live_encrypted)
    else:
        keys_ok = bool(ps.paypal_client_id_sandbox and ps.paypal_client_secret_sandbox_encrypted)
    
    # Step 3: Plans validation (all 3 plans)
    if ps.paypal_mode == "live":
        plans_ok = all([
            ps.paypal_plan_id_starter_live,
            ps.paypal_plan_id_business_live,
            ps.paypal_plan_id_enterprise_live
        ])
    else:
        plans_ok = all([
            ps.paypal_plan_id_starter_sandbox,
            ps.paypal_plan_id_business_sandbox,
            ps.paypal_plan_id_enterprise_sandbox
        ])
    
    # Step 4: Webhook validation
    if ps.paypal_mode == "live":
        webhook_ok = bool(ps.paypal_webhook_id_live)
    else:
        webhook_ok = bool(ps.paypal_webhook_id_sandbox)
    
    # Step 5: Events validation
    from django.utils import timezone
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    received_event_ok = PayPalEvent.objects.filter(created_at__gte=thirty_days_ago).exists()
    
    # Get latest event for display
    latest_event = PayPalEvent.objects.order_by('-created_at').first()
    latest_event_info = {
        "exists": latest_event is not None,
        "event_type": latest_event.event_type if latest_event else None,
        "created_at": latest_event.created_at.isoformat() if latest_event else None,
        "verified": latest_event.verified if latest_event else False
    }
    
    # Webhook URL
    webhook_url = cfg["webhook_url"] if domain_ok else ""
    
    validation_result = {
        "domain_ok": domain_ok,
        "keys_ok": keys_ok,
        "plans_ok": plans_ok,
        "webhook_ok": webhook_ok,
        "received_event_ok": received_event_ok,
        "webhook_url": webhook_url,
        "latest_event": latest_event_info,
        "overall_ok": all([domain_ok, keys_ok, plans_ok, webhook_ok, received_event_ok])
    }
    
    return JsonResponse({"ok": True, "validation": validation_result})


@require_superadmin
def setup_status(request: HttpRequest) -> JsonResponse:
    """AJAX: return current setup status for all 5 steps."""
    cfg = get_paypal_config()
    ps = PlatformSettings.get()
    has_events = PayPalEvent.objects.exists()

    return JsonResponse({
        "step1": bool(cfg["base_url"]),
        "step2": bool(cfg["client_id"] and ps.active_client_secret_encrypted),
        "step3": bool(cfg["plan_id"]),
        "step4": bool(cfg["webhook_url"]),
        "step5": has_events,
    })


# ═══════════════════════════════════════════════════════════════════════
# ADMIN ALERTS
# ═══════════════════════════════════════════════════════════════════════

@require_superadmin
def alerts_list(request: HttpRequest) -> HttpResponse:
    """Admin alerts page with filter and mark-as-read."""
    qs = AdminAlert.objects.select_related("agency").all()

    # Filters
    filter_type = request.GET.get("type", "")
    filter_read = request.GET.get("read", "")
    if filter_type:
        qs = qs.filter(alert_type=filter_type)
    if filter_read == "0":
        qs = qs.filter(is_read=False)
    elif filter_read == "1":
        qs = qs.filter(is_read=True)

    alerts = qs[:100]
    unread_count = AdminAlert.objects.filter(is_read=False).count()

    return render(request, "superadmin/alerts.html", {
        "page_id": "alerts",
        "alerts": alerts,
        "unread_count": unread_count,
        "filter_type": filter_type,
        "filter_read": filter_read,
        "type_choices": AdminAlert.TYPE_CHOICES,
    })


@require_superadmin
def alert_mark_read(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a single alert as read."""
    if request.method == "POST":
        alert = get_object_or_404(AdminAlert, pk=pk)
        alert.is_read = True
        alert.save(update_fields=["is_read"])
    return redirect(request.POST.get("next", "superadmin:alerts"))


@require_superadmin
def alerts_mark_all_read(request: HttpRequest) -> HttpResponse:
    """Mark all unread alerts as read."""
    if request.method == "POST":
        AdminAlert.objects.filter(is_read=False).update(is_read=True)
    return redirect("superadmin:alerts")
