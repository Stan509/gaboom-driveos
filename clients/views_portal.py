import base64
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from agencies.models import Agency, GPSPositionLog, ReservationRequest
from agencies.services import get_agency_access
from billing.models import Contract
from clients.decorators import (
    SESSION_AGENCY,
    SESSION_KEY,
    get_client_from_session,
    require_client_login,
)
from clients.models import ClientAccount, ClientNotification


# ── helpers ──────────────────────────────────────────────────────────

def _get_agency(slug):
    return get_object_or_404(Agency, slug=slug, public_enabled=True)


def _portal_enabled(agency: Agency) -> bool:
    access = get_agency_access(agency)
    return access.plan_has_feature("client_portal")


def _loyalty_enabled(agency: Agency) -> bool:
    access = get_agency_access(agency)
    return access.plan_has_feature("loyalty")

def _gps_enabled(agency: Agency) -> bool:
    access = get_agency_access(agency)
    return access.plan_has_feature("gps_tracking")


def _portal_ctx(request, slug, agency=None):
    """Base context for client portal templates."""
    if agency is None:
        agency = _get_agency(slug)
    from public_site.views import _theme_ctx
    ctx = _theme_ctx(agency, request)
    ca = getattr(request, "client_account", None)
    ctx["client_account"] = ca
    ctx["gps_enabled"] = _gps_enabled(agency)
    ctx["portal_disabled"] = not _portal_enabled(agency)
    if ca:
        ctx["unread_notifs"] = ClientNotification.objects.filter(client=ca, is_read=False).count()
    return ctx


# ── Auth views ───────────────────────────────────────────────────────

def client_signup(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _get_agency(slug)
    if not _portal_enabled(agency):
        ctx = _portal_ctx(request, slug, agency)
        ctx["portal_disabled"] = True  # Forcer l'affichage du message d'erreur
        return render(request, "client_portal/_base.html", ctx)
    
    ctx = _portal_ctx(request, slug, agency)

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()[:255]
        email = request.POST.get("email", "").strip().lower()[:254]
        phone = request.POST.get("phone", "").strip()[:30]
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")

        errors = {}
        if not full_name:
            errors["full_name"] = "Le nom est requis."
        if not email:
            errors["email"] = "L'email est requis."
        if len(password) < 6:
            errors["password"] = "Le mot de passe doit contenir au moins 6 caractères."
        if password != password2:
            errors["password2"] = "Les mots de passe ne correspondent pas."

        if not errors and ClientAccount.objects.filter(agency=agency, email=email).exists():
            errors["email"] = "Un compte existe déjà avec cet email."

        if errors:
            ctx["errors"] = errors
            ctx["form_data"] = request.POST
            return render(request, "client_portal/signup.html", ctx)

        account = ClientAccount(agency=agency, email=email, full_name=full_name, phone=phone)
        account.set_password(password)
        account.save()

        # Auto-login
        request.session[SESSION_KEY] = account.pk
        request.session[SESSION_AGENCY] = slug
        next_url = request.POST.get("next") or request.GET.get("next", "")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect("public_site:client_dashboard", slug=slug)

    return render(request, "client_portal/signup.html", ctx)


def client_login(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _get_agency(slug)
    if not _portal_enabled(agency):
        ctx = _portal_ctx(request, slug, agency)
        ctx["portal_disabled"] = True  # Forcer l'affichage du message d'erreur
        return render(request, "client_portal/_base.html", ctx)
    ctx = _portal_ctx(request, slug, agency)

    # Already logged in?
    existing = get_client_from_session(request, slug)
    if existing:
        return redirect("public_site:client_dashboard", slug=slug)

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        account = ClientAccount.objects.filter(agency=agency, email=email, is_active=True).first()
        if account and account.check_password(password):
            request.session[SESSION_KEY] = account.pk
            request.session[SESSION_AGENCY] = slug
            next_url = request.POST.get("next") or request.GET.get("next", "")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect("public_site:client_dashboard", slug=slug)

        ctx["error"] = "Email ou mot de passe incorrect."
        ctx["form_data"] = request.POST

    return render(request, "client_portal/login.html", ctx)


def client_logout(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _get_agency(slug)
    if not _portal_enabled(agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    request.session.pop(SESSION_KEY, None)
    request.session.pop(SESSION_AGENCY, None)
    return redirect("public_site:agency_public_home", slug=slug)


# ── Portal pages ─────────────────────────────────────────────────────

@require_client_login
def client_dashboard(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _get_agency(slug)
    if not _portal_enabled(agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)
    ca = request.client_account

    reservations = ReservationRequest.objects.filter(
        agency=ca.agency, client_account=ca,
    ).order_by("-created_at")

    ctx["reservations_pending"] = reservations.filter(status="pending").count()
    ctx["reservations_confirmed"] = reservations.filter(status="confirmed").count()
    ctx["reservations_recent"] = reservations[:5]
    ctx["unread_notifs"] = ClientNotification.objects.filter(client=ca, is_read=False).count()
    ctx["page_id"] = "dashboard"

    # Loyalty
    from clients.models import ClientLoyalty
    if _loyalty_enabled(ca.agency):
        loyalty, _ = ClientLoyalty.objects.get_or_create(client=ca)
        ctx["loyalty"] = loyalty

    return render(request, "client_portal/dashboard.html", ctx)


@require_client_login
def client_bookings(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _get_agency(slug)
    if not _portal_enabled(agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)
    ca = request.client_account

    status_filter = request.GET.get("status", "")
    qs = ReservationRequest.objects.filter(agency=ca.agency, client_account=ca).order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)

    ctx["reservations"] = qs
    ctx["status_filter"] = status_filter
    ctx["status_choices"] = [("pending", "En attente"), ("confirmed", "Confirmées"), ("rejected", "Refusées")]
    ctx["page_id"] = "bookings"
    return render(request, "client_portal/bookings.html", ctx)


@require_client_login
def client_profile(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _get_agency(slug)
    if not _portal_enabled(agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)
    ca = request.client_account

    ctx["page_id"] = "profile"

    if request.method == "POST":
        ca.full_name = request.POST.get("full_name", ca.full_name).strip()[:255]
        ca.phone = request.POST.get("phone", ca.phone).strip()[:30]

        new_pw = request.POST.get("new_password", "")
        if new_pw:
            if len(new_pw) < 6:
                ctx["error"] = "Le mot de passe doit contenir au moins 6 caractères."
                return render(request, "client_portal/profile.html", ctx)
            ca.set_password(new_pw)

        ca.save()
        ctx["success"] = "Profil mis à jour."

    return render(request, "client_portal/profile.html", ctx)


@require_client_login
def client_notifications(request: HttpRequest, slug: str) -> HttpResponse:
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)

    notifs = ClientNotification.objects.filter(client=ca)
    ctx["notifications"] = notifs[:50]
    ctx["unread_count"] = notifs.filter(is_read=False).count()
    ctx["page_id"] = "notifications"

    # Mark all as read on visit
    notifs.filter(is_read=False).update(is_read=True)

    return render(request, "client_portal/notifications.html", ctx)


# ── Negotiation actions ──────────────────────────────────────────────

@require_client_login
def client_accept_counter(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """Client accepts the agency's counter-offer."""
    if request.method != "POST":
        return redirect("public_site:client_bookings", slug=slug)
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    r = get_object_or_404(
        ReservationRequest.objects.filter(agency=ca.agency, client_account=ca), pk=pk,
    )
    if r.negotiation_status != "countered":
        messages.error(request, "Aucune contre-offre en attente.")
        return redirect("public_site:client_bookings", slug=slug)

    from agencies.models import has_date_conflict
    from django.db import transaction

    with transaction.atomic():
        if has_date_conflict(r.vehicle, r.start_date, r.end_date, exclude_pk=pk):
            messages.error(request, "Conflit de dates détecté pour ce véhicule.")
            return redirect("public_site:client_bookings", slug=slug)
        r.daily_price_accepted = r.daily_price_counter
        r.negotiation_status = "accepted"
        r.status = "confirmed"
        r.decision_message = "Contre-offre acceptée par le client."
        r.save(update_fields=[
            "daily_price_accepted", "negotiation_status",
            "status", "decision_message", "updated_at",
        ])

    ClientNotification.objects.create(
        client=ca,
        title="Réservation confirmée",
        message=f"Vous avez accepté la contre-offre de {r.daily_price_counter}/jour pour {r.vehicle}. Réservation confirmée !",
        notif_type="success",
    )
    messages.success(request, "Contre-offre acceptée — réservation confirmée !")
    return redirect("public_site:client_bookings", slug=slug)


@require_client_login
def client_refuse_counter(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """Client refuses the agency's counter-offer."""
    if request.method != "POST":
        return redirect("public_site:client_bookings", slug=slug)
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    r = get_object_or_404(
        ReservationRequest.objects.filter(agency=ca.agency, client_account=ca), pk=pk,
    )
    if r.negotiation_status != "countered":
        messages.error(request, "Aucune contre-offre en attente.")
        return redirect("public_site:client_bookings", slug=slug)

    r.negotiation_status = "refused"
    r.status = "rejected"
    r.decision_message = "Contre-offre refusée par le client."
    r.save(update_fields=[
        "negotiation_status", "status", "decision_message", "updated_at",
    ])

    ClientNotification.objects.create(
        client=ca,
        title="Réservation annulée",
        message=f"Vous avez refusé la contre-offre pour {r.vehicle}. La réservation est annulée.",
        notif_type="warn",
    )
    messages.success(request, "Contre-offre refusée — réservation annulée.")
    return redirect("public_site:client_bookings", slug=slug)


# ── Contract views ───────────────────────────────────────────────────

@require_client_login
def client_contracts(request: HttpRequest, slug: str) -> HttpResponse:
    """List contracts for the logged-in client."""
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)
    contracts = Contract.objects.filter(
        agency=ca.agency, client_account=ca,
    ).select_related("vehicle").order_by("-created_at")
    ctx["contracts"] = contracts
    ctx["page_id"] = "contracts"
    return render(request, "client_portal/contracts.html", ctx)


@require_client_login
def client_contract_detail(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """View contract details."""
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)
    contract = get_object_or_404(
        Contract.objects.filter(agency=ca.agency, client_account=ca).select_related(
            "vehicle", "client",
        ),
        pk=pk,
    )
    ctx["contract"] = contract
    ctx["page_id"] = "contracts"
    return render(request, "client_portal/contract_detail.html", ctx)


@require_client_login
def client_contract_sign(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """Client signs the contract with a digital signature."""
    if request.method != "POST":
        return redirect("public_site:client_contract_detail", slug=slug, pk=pk)

    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    contract = get_object_or_404(
        Contract.objects.filter(agency=ca.agency, client_account=ca),
        pk=pk,
    )

    if not contract.can_sign:
        messages.error(request, "Ce contrat ne peut pas être signé.")
        return redirect("public_site:client_contract_detail", slug=slug, pk=pk)

    # Parse base64 signature image from canvas
    sig_data = request.POST.get("signature", "")
    if not sig_data or "base64," not in sig_data:
        messages.error(request, "Veuillez dessiner votre signature.")
        return redirect("public_site:client_contract_detail", slug=slug, pk=pk)

    # Decode base64 → image file
    fmt, imgstr = sig_data.split(";base64,")
    ext = fmt.split("/")[-1]
    if ext not in ("png", "jpeg", "webp"):
        ext = "png"
    file_name = f"sig_contract_{contract.pk}_{ca.pk}.{ext}"
    sig_file = ContentFile(base64.b64decode(imgstr), name=file_name)

    contract.client_signature = sig_file
    contract.client_signed_at = timezone.now()
    # Get client IP
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        contract.client_signed_ip = x_forwarded.split(",")[0].strip()
    else:
        contract.client_signed_ip = request.META.get("REMOTE_ADDR")
    contract.save(update_fields=[
        "client_signature", "client_signed_at", "client_signed_ip",
    ])

    ClientNotification.objects.create(
        client=ca,
        title="Contrat signé",
        message=f"Vous avez signé le contrat #{contract.pk} pour {contract.vehicle}.",
        notif_type="success",
    )
    messages.success(request, "Contrat signé avec succès !")
    return redirect("public_site:client_contract_detail", slug=slug, pk=pk)


# ── GPS Position Sharing (client side) ────────────────────────────────

@require_client_login
def client_gps_tracking(request: HttpRequest, slug: str) -> HttpResponse:
    """Client AI driving assistant — interactive map with AI coaching.
    Also shares client phone position with the agency when GPS is enabled."""
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    if not _gps_enabled(ca.agency):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    ctx = _portal_ctx(request, slug)
    
    # Find active contract for this client
    contract = (
        Contract.objects.filter(
            agency=ca.agency, client_account=ca, status="active",
        )
        .select_related("vehicle")
        .first()
    )
    ctx["contract"] = contract
    ctx["page_id"] = "gps"

    # ALWAYS show the AI driving map, even without contract
    # Position sharing to the agency is only available with active contract
    if contract and contract.vehicle:
        gps_on = contract.vehicle.gps_enabled
        is_phone = contract.vehicle.gps_source == "phone"
        has_consent = bool(contract.gps_consent_signed_at)
        needs_consent = gps_on and is_phone and not has_consent
        ctx["show_driving_map"] = True
        ctx["needs_consent"] = needs_consent
        ctx["gps_source"] = contract.vehicle.gps_source if gps_on else ""
        ctx["gps_consent_signed"] = has_consent
        ctx["share_with_agency"] = gps_on and is_phone and has_consent
        ctx["local_only_mode"] = not gps_on
        ctx["has_contract"] = True
    else:
        # Show AI driving map in demo mode without contract
        ctx["show_driving_map"] = True
        ctx["needs_consent"] = False
        ctx["gps_source"] = ""
        ctx["gps_consent_signed"] = False
        ctx["share_with_agency"] = False
        ctx["local_only_mode"] = True  # Always local mode without contract
        ctx["has_contract"] = False

    return render(request, "client_portal/gps_tracking.html", ctx)


@require_client_login
def client_gps_consent(request: HttpRequest, slug: str) -> HttpResponse:
    """Client signs GPS tracking consent — required before phone GPS sharing starts."""
    if request.method != "POST":
        return redirect("public_site:client_gps_tracking", slug=slug)

    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return HttpResponseForbidden("Portail client non disponible pour ce plan.")
    if not _gps_enabled(ca.agency):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    contract = (
        Contract.objects.filter(
            agency=ca.agency, client_account=ca, status="active",
        )
        .select_related("vehicle")
        .first()
    )
    if not contract:
        messages.error(request, "Aucun contrat actif trouvé.")
        return redirect("public_site:client_gps_tracking", slug=slug)

    if contract.gps_consent_signed_at:
        messages.info(request, "Vous avez déjà accepté le suivi GPS.")
        return redirect("public_site:client_gps_tracking", slug=slug)

    # Record consent
    contract.gps_consent_signed_at = timezone.now()
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        contract.gps_consent_ip = x_forwarded.split(",")[0].strip()
    else:
        contract.gps_consent_ip = request.META.get("REMOTE_ADDR")
    contract.save(update_fields=["gps_consent_signed_at", "gps_consent_ip"])

    ClientNotification.objects.create(
        client=ca,
        title="Consentement GPS accepté",
        message=f"Vous avez accepté le suivi GPS pour le contrat #{contract.pk} ({contract.vehicle}). Votre position sera partagée avec l'agence pendant la durée du contrat.",
        notif_type="info",
    )
    messages.success(request, "Consentement GPS enregistré. Le partage de position va démarrer.")
    return redirect("public_site:client_gps_tracking", slug=slug)


@csrf_exempt
def client_gps_share(request: HttpRequest, slug: str) -> JsonResponse:
    """API endpoint — client's phone sends its GPS position to the agency.
    Used when gps_source == 'phone'. Requires GPS consent to be signed.
    The agency can then track the vehicle from the admin dashboard."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    ca = get_client_from_session(request)
    if not ca:
        return JsonResponse({"error": "Not authenticated"}, status=401)
    if not _portal_enabled(ca.agency):
        return JsonResponse({"error": "Portail client non disponible pour ce plan."}, status=403)
    if not _gps_enabled(ca.agency):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return JsonResponse({"error": "lat and lng required"}, status=400)

    # Find active contract
    contract = (
        Contract.objects.filter(
            agency=ca.agency, client_account=ca, status="active",
        )
        .select_related("vehicle")
        .first()
    )
    if not contract or not contract.vehicle:
        return JsonResponse({"error": "No active contract"}, status=404)

    vehicle = contract.vehicle
    if vehicle.gps_source != "phone":
        return JsonResponse({"error": "GPS source is not phone"}, status=400)

    # Require GPS consent before accepting position data
    if not contract.gps_consent_signed_at:
        return JsonResponse({"error": "GPS consent not signed"}, status=403)

    now = timezone.now()
    speed = data.get("speed")
    heading = data.get("heading")

    # Update vehicle position (agency sees this on their dashboard)
    vehicle.last_lat = Decimal(str(lat))
    vehicle.last_lng = Decimal(str(lng))
    vehicle.last_gps_speed = Decimal(str(speed)) if speed is not None else None
    vehicle.last_gps_update = now
    vehicle.gps_enabled = True
    vehicle.save(update_fields=["last_lat", "last_lng", "last_gps_speed", "last_gps_update", "gps_enabled"])

    # Log position
    GPSPositionLog.objects.create(
        vehicle=vehicle,
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
        speed=Decimal(str(speed)) if speed is not None else None,
        heading=Decimal(str(heading)) if heading is not None else None,
        source="phone",
        recorded_at=now,
    )

    return JsonResponse({"status": "ok"})


@require_client_login
def client_vehicle_trail(request: HttpRequest, slug: str) -> JsonResponse:
    ca = request.client_account
    if not _portal_enabled(ca.agency):
        return JsonResponse({"error": "Portail client non disponible pour ce plan."}, status=403)
    if not _gps_enabled(ca.agency):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)

    contract = (
        Contract.objects.filter(
            agency=ca.agency, client_account=ca, status="active",
        )
        .select_related("vehicle")
        .first()
    )
    if not contract or not contract.vehicle:
        return JsonResponse({"error": "No active contract"}, status=404)

    hours = int(request.GET.get("hours", 24))
    since = timezone.now() - timedelta(hours=hours)
    logs = GPSPositionLog.objects.filter(
        vehicle=contract.vehicle, recorded_at__gte=since,
    ).order_by("recorded_at")[:500]
    trail = [
        {
            "lat": float(log.lat),
            "lng": float(log.lng),
            "speed": float(log.speed) if log.speed else 0,
            "ts": log.recorded_at.isoformat(),
        }
        for log in logs
    ]
    return JsonResponse({"trail": trail})
