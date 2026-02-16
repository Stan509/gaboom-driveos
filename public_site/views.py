from datetime import date
from decimal import Decimal

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from agencies.models import (
    Agency, AgencySiteSection, AgencySiteSettings,
    BusinessSettings, PromoCode, SiteBanner,
    ReservationRequest, Vehicle, has_date_conflict,
)
from agencies.services import get_agency_access
from agencies.theme_presets import THEMES_BY_ID
from clients.decorators import get_client_from_session
from public_site.markdown_utils import render_markdown
from public_site.models import PublicPage


# ── helpers ──────────────────────────────────────────────────────────

def _get_business_settings(agency: Agency):
    try:
        return agency.business_settings
    except BusinessSettings.DoesNotExist:
        return None


def _get_site_settings(agency: Agency):
    """Return AgencySiteSettings, creating with defaults if missing."""
    try:
        return agency.site_settings
    except AgencySiteSettings.DoesNotExist:
        ss = AgencySiteSettings.objects.create(agency=agency)
        ss.ensure_defaults()
        ss.save()
        return ss


def _booking_enabled(agency: Agency) -> bool:
    access = get_agency_access(agency)
    return access.plan_has_feature("online_booking")


def _resolve_agency(slug: str, request: HttpRequest | None = None) -> Agency:
    """Resolve agency by slug. In preview mode (logged-in owner), allow draft."""
    agency = get_object_or_404(Agency, slug=slug)
    preview = request and request.GET.get("preview") == "1"

    if preview:
        # Preview allowed for logged-in users of this agency
        if request.user.is_authenticated and hasattr(request.user, "agency") and request.user.agency_id == agency.pk:
            return agency
        # Also allow superusers
        if request.user.is_authenticated and request.user.is_superuser:
            return agency

    # Normal access: check public_enabled via site_settings (with agency fallback)
    ss = _get_site_settings(agency)
    if not ss.is_public_enabled and not agency.public_enabled:
        raise Http404("Agence introuvable")
    return agency


def _theme_ctx(agency: Agency, request=None) -> dict:
    ss = _get_site_settings(agency)
    preset = THEMES_BY_ID.get(ss.theme_key, THEMES_BY_ID.get(agency.theme, THEMES_BY_ID["default"]))
    primary = ss.primary_color or agency.primary_color or preset["primary"]
    secondary = ss.secondary_color or agency.secondary_color or preset["secondary"]
    sections = AgencySiteSection.objects.filter(agency=agency, page="home").order_by("order")
    enabled_keys = {s.key for s in sections if s.enabled}
    nav_pages = PublicPage.objects.for_agency(agency).in_nav()
    legal_pages = PublicPage.objects.for_agency(agency).legal()
    footer_pages = PublicPage.objects.for_agency(agency).published().exclude(
        template_variant="legal", show_in_nav=False,
    ).order_by("nav_order", "title")[:10]

    # Client portal session
    client_account = None
    if request:
        client_account = get_client_from_session(request, agency.slug)

    return {
        "agency": agency,
        "ss": ss,
        "theme": preset,
        "primary": primary,
        "secondary": secondary,
        "bg": preset["bg"],
        "card_bg": preset["card_bg"],
        "text_color": preset["text"],
        "style": preset["style"],
        "font": ss.font_family or "Inter",
        "sections_enabled": enabled_keys,
        "nav_pages": nav_pages,
        "footer_pages": footer_pages,
        "legal_pages": legal_pages,
        "client_account": client_account,
        "banners": SiteBanner.objects.filter(agency=agency, active=True),
    }


def _handle_maintenance(request: HttpRequest, agency: Agency) -> HttpResponse | None:
    preview = request.GET.get("preview") == "1"
    if preview:
        return None
    ss = _get_site_settings(agency)
    if ss.is_maintenance_enabled or agency.maintenance_mode:
        return render(request, "public_site/maintenance.html", _theme_ctx(agency, request))
    return None


def _available_vehicles(agency: Agency):
    return Vehicle.objects.for_agency(agency).filter(public_visible=True, status="available")


# ── views ────────────────────────────────────────────────────────────

def agency_public_home(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    maintenance = _handle_maintenance(request, agency)
    if maintenance:
        return maintenance

    vehicles = _available_vehicles(agency)[:6]
    ctx = _theme_ctx(agency, request)
    ctx["vehicles"] = vehicles
    return render(request, "public_site/agency_home.html", ctx)


def agency_catalog(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    maintenance = _handle_maintenance(request, agency)
    if maintenance:
        return maintenance

    vehicles = _available_vehicles(agency)
    ctx = _theme_ctx(agency, request)
    ctx["vehicles"] = vehicles
    bs = _get_business_settings(agency)
    ctx["agency_allows_negotiation"] = bs.allow_price_negotiation if bs else False
    ctx["currency"] = bs.currency if bs else "EUR"
    return render(request, "public_site/catalog.html", ctx)


def vehicle_detail(request: HttpRequest, slug: str, vehicle_id: int) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    maintenance = _handle_maintenance(request, agency)
    if maintenance:
        return maintenance

    vehicle = get_object_or_404(Vehicle.objects.for_agency(agency), pk=vehicle_id, public_visible=True)
    ctx = _theme_ctx(agency, request)
    ctx["vehicle"] = vehicle
    bs = _get_business_settings(agency)
    agency_allows = bs.allow_price_negotiation if bs else False
    ctx["allow_negotiation"] = agency_allows and vehicle.allow_negotiation
    ctx["currency"] = bs.currency if bs else "EUR"
    return render(request, "public_site/vehicle_detail.html", ctx)


def vehicle_book(request: HttpRequest, slug: str) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    maintenance = _handle_maintenance(request, agency)
    if maintenance:
        return maintenance
    if not _booking_enabled(agency):
        raise Http404("Module de réservation indisponible")

    return render(request, "public_site/book.html", _theme_ctx(agency, request))


# ── Reservation views ────────────────────────────────────────────────

def reserve_vehicle(request: HttpRequest, slug: str, vehicle_id: int) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    maintenance = _handle_maintenance(request, agency)
    if maintenance:
        return maintenance
    if not _booking_enabled(agency):
        raise Http404("Module de réservation indisponible")

    vehicle = get_object_or_404(
        Vehicle.objects.for_agency(agency), pk=vehicle_id, public_visible=True,
    )
    ctx = _theme_ctx(agency, request)
    ctx["vehicle"] = vehicle
    ctx["today"] = date.today().isoformat()

    # Block reservation if vehicle is not available
    if vehicle.status != "available":
        ctx["vehicle_unavailable"] = True
        return render(request, "public_site/reserve_form.html", ctx)

    # Negotiation context: agency-level AND vehicle-level must both allow it
    bs = _get_business_settings(agency)
    agency_allows = bs.allow_price_negotiation if bs else False
    allow_nego = agency_allows and vehicle.allow_negotiation
    min_pct = bs.negotiation_min_percent if bs else 70
    currency = bs.currency if bs else "EUR"
    min_offer = (vehicle.daily_price * min_pct / 100).quantize(Decimal("0.01")) if vehicle.daily_price else Decimal("0")
    client_acct = get_client_from_session(request, slug)
    ctx["client_account"] = client_acct
    ctx["allow_negotiation"] = allow_nego
    ctx["client_logged_in"] = client_acct is not None
    ctx["negotiation_min_percent"] = min_pct
    ctx["min_offer_price"] = min_offer
    ctx["currency"] = currency

    if request.method == "POST":
        # Honeypot anti-spam
        if request.POST.get("website", "").strip():
            return render(request, "public_site/reserve_form.html", ctx)

        phone = request.POST.get("phone", "").strip()[:30]
        email = request.POST.get("email", "").strip()[:254]
        start_date_str = request.POST.get("start_date", "")
        end_date_str = request.POST.get("end_date", "")
        message = request.POST.get("message", "").strip()[:500]

        errors = {}
        if not phone:
            errors["phone"] = "Le numéro de téléphone est requis."
        if not email:
            errors["email"] = "L'email est requis."

        try:
            start_dt = date.fromisoformat(start_date_str)
        except (ValueError, TypeError):
            errors["start_date"] = "Date de début invalide."
            start_dt = None
        try:
            end_dt = date.fromisoformat(end_date_str)
        except (ValueError, TypeError):
            errors["end_date"] = "Date de fin invalide."
            end_dt = None

        if start_dt and end_dt:
            if end_dt < start_dt:
                errors["end_date"] = "La date de fin doit être après la date de début."
            elif start_dt < date.today():
                errors["start_date"] = "La date de début ne peut pas être dans le passé."

        # Negotiation offer validation (requires login)
        want_negotiate = allow_nego and request.POST.get("want_negotiate") == "1" and client_acct is not None
        price_offer = None
        nego_msg = ""
        if want_negotiate:
            try:
                price_offer = Decimal(request.POST.get("price_offer", "0"))
            except Exception:
                price_offer = None
                errors["price_offer"] = "Prix invalide."
            if price_offer is not None:
                if price_offer < min_offer:
                    errors["price_offer"] = f"L'offre minimum est {min_offer} {currency}."
                elif price_offer <= 0:
                    errors["price_offer"] = "Le prix doit être supérieur à 0."
            nego_msg = request.POST.get("negotiation_message", "").strip()[:500]

        # Promo code validation
        promo_code_str = request.POST.get("promo_code", "").strip().upper()
        promo = None
        if promo_code_str:
            promo = PromoCode.objects.filter(agency=agency, code=promo_code_str).first()
            if not promo:
                errors["promo_code"] = "Code promo invalide."
            elif not promo.is_valid:
                errors["promo_code"] = "Ce code promo a expiré ou atteint sa limite."

        if errors:
            ctx["errors"] = errors
            ctx["form_data"] = request.POST
            return render(request, "public_site/reserve_form.html", ctx)

        # Check date conflict
        if start_dt and end_dt and has_date_conflict(vehicle, start_dt, end_dt):
            alternatives = (
                Vehicle.objects.for_agency(agency)
                .filter(public_visible=True)
                .exclude(pk=vehicle.pk)
                .exclude(
                    reservation_requests__status="confirmed",
                    reservation_requests__start_date__lte=end_dt,
                    reservation_requests__end_date__gte=start_dt,
                )
                .distinct()[:3]
            )
            ctx["conflict"] = True
            ctx["alternatives"] = alternatives
            ctx["form_data"] = request.POST
            return render(request, "public_site/reserve_form.html", ctx)

        # Create reservation
        reservation = ReservationRequest(
            agency=agency,
            vehicle=vehicle,
            full_name="",
            phone=phone,
            email=email,
            whatsapp="",
            start_date=start_dt,
            end_date=end_dt,
            message=message,
            source="public_site",
            client_account=client_acct,
            daily_price_official=vehicle.daily_price,
        )
        if want_negotiate and price_offer:
            reservation.daily_price_offer = price_offer
            reservation.negotiation_status = "pending_offer"
            reservation.negotiation_message = nego_msg
        reservation.save()

        # Apply promo code
        if promo:
            promo.usage_count += 1
            promo.save(update_fields=["usage_count"])

        # Client notification
        if client_acct:
            from clients.models import ClientNotification
            notif_msg = f"Demande de réservation envoyée pour {vehicle} du {start_dt} au {end_dt}."
            if want_negotiate and price_offer:
                notif_msg += f" Offre de {price_offer} {currency}/jour envoyée."
            ClientNotification.objects.create(
                client=client_acct,
                title="Demande envoyée",
                message=notif_msg,
                notif_type="info",
            )

        # Send email notification to admins
        _notify_admin_new_reservation(reservation)

        return redirect(
            f"/a/{agency.slug}/reservation/{reservation.public_token}/"
            f"?s={reservation.public_secret}"
        )

    return render(request, "public_site/reserve_form.html", ctx)


def reservation_status(request: HttpRequest, slug: str, token: str) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency), public_token=token,
    )
    secret = request.GET.get("s", "")
    if not reservation.verify_secret(secret):
        raise Http404("Lien invalide")

    # Mark as seen
    if not reservation.client_seen_at:
        reservation.client_seen_at = timezone.now()
        reservation.save(update_fields=["client_seen_at"])

    # Negotiation messages
    from clients.models import NegotiationMessage
    nego_messages = NegotiationMessage.objects.filter(reservation=reservation)
    # Mark agency messages as read by client
    nego_messages.filter(sender="agency", is_read=False).update(is_read=True)

    client_acct = get_client_from_session(request, slug)
    can_chat = reservation.client_account and client_acct and client_acct.pk == reservation.client_account_id

    ctx = _theme_ctx(agency, request)
    ctx["reservation"] = reservation
    ctx["secret"] = secret
    ctx["nego_messages"] = nego_messages
    ctx["can_chat"] = can_chat
    return render(request, "public_site/reservation_status.html", ctx)


def reservation_poll(request: HttpRequest, slug: str, token: str) -> JsonResponse:
    agency = get_object_or_404(Agency, slug=slug)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency), public_token=token,
    )
    secret = request.GET.get("s", "")
    if not reservation.verify_secret(secret):
        return JsonResponse({"error": "forbidden"}, status=403)

    from clients.models import NegotiationMessage
    msg_count = NegotiationMessage.objects.filter(reservation=reservation).count()
    unread_agency = NegotiationMessage.objects.filter(
        reservation=reservation, sender="agency", is_read=False,
    ).count()

    return JsonResponse({
        "status": reservation.status,
        "status_display": reservation.get_status_display(),
        "negotiation_status": reservation.negotiation_status,
        "decision_message": reservation.decision_message,
        "updated_at": reservation.updated_at.isoformat(),
        "msg_count": msg_count,
        "unread_agency_msgs": unread_agency,
    })


@require_POST
def reservation_send_message(request: HttpRequest, slug: str, token: str) -> HttpResponse:
    """Client sends a negotiation chat message to the agency."""
    agency, reservation = _verify_reservation_secret(request, slug, token)
    secret = request.POST.get("s", "")

    # Must be logged in as the reservation's client
    client_acct = get_client_from_session(request, slug)
    if not client_acct or not reservation.client_account or client_acct.pk != reservation.client_account_id:
        raise Http404("Non autorisé")

    body = request.POST.get("body", "").strip()[:1000]
    if not body:
        return redirect(f"/a/{agency.slug}/reservation/{reservation.public_token}/?s={secret}")

    from clients.models import NegotiationMessage
    NegotiationMessage.objects.create(
        reservation=reservation, sender="client", body=body,
    )

    return redirect(f"/a/{agency.slug}/reservation/{reservation.public_token}/?s={secret}")


def _verify_reservation_secret(request, slug, token):
    """Helper: resolve reservation + verify secret. Returns (agency, reservation) or raises Http404."""
    agency = _resolve_agency(slug, request)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency), public_token=token,
    )
    secret = request.POST.get("s") or request.GET.get("s", "")
    if not reservation.verify_secret(secret):
        raise Http404("Lien invalide")
    return agency, reservation


@require_POST
def reservation_accept_counter(request: HttpRequest, slug: str, token: str) -> HttpResponse:
    """Client accepts the agency's counter-offer via public tracking link."""
    agency, r = _verify_reservation_secret(request, slug, token)
    secret = request.POST.get("s", "")

    if r.negotiation_status != "countered":
        return redirect(f"/a/{agency.slug}/reservation/{r.public_token}/?s={secret}")

    from django.db import transaction

    with transaction.atomic():
        if has_date_conflict(r.vehicle, r.start_date, r.end_date, exclude_pk=r.pk):
            return redirect(f"/a/{agency.slug}/reservation/{r.public_token}/?s={secret}")
        r.daily_price_accepted = r.daily_price_counter
        r.negotiation_status = "accepted"
        r.status = "confirmed"
        r.decision_message = f"Contre-offre de {r.daily_price_counter}/jour acceptée par le client."
        r.save(update_fields=[
            "daily_price_accepted", "negotiation_status",
            "status", "decision_message", "updated_at",
        ])
        # Auto-set vehicle to rented
        vehicle = r.vehicle
        if vehicle.status == "available":
            vehicle.status = "rented"
            vehicle.save(update_fields=["status"])

    # Client notification if logged in
    if r.client_account:
        from clients.models import ClientNotification
        ClientNotification.objects.create(
            client=r.client_account,
            title="Réservation confirmée",
            message=f"Vous avez accepté la contre-offre de {r.daily_price_counter}/jour pour {r.vehicle}. Réservation confirmée !",
            notif_type="success",
        )

    return redirect(f"/a/{agency.slug}/reservation/{r.public_token}/?s={secret}")


@require_POST
def reservation_reject_counter(request: HttpRequest, slug: str, token: str) -> HttpResponse:
    """Client rejects the agency's counter-offer via public tracking link."""
    agency, r = _verify_reservation_secret(request, slug, token)
    secret = request.POST.get("s", "")

    if r.negotiation_status != "countered":
        return redirect(f"/a/{agency.slug}/reservation/{r.public_token}/?s={secret}")

    r.negotiation_status = "refused"
    r.status = "rejected"
    r.decision_message = "Contre-offre refusée par le client."
    r.save(update_fields=[
        "negotiation_status", "status", "decision_message", "updated_at",
    ])

    if r.client_account:
        from clients.models import ClientNotification
        ClientNotification.objects.create(
            client=r.client_account,
            title="Réservation annulée",
            message=f"Vous avez refusé la contre-offre pour {r.vehicle}. La réservation est annulée.",
            notif_type="warn",
        )

    return redirect(f"/a/{agency.slug}/reservation/{r.public_token}/?s={secret}")


def _notify_admin_new_reservation(reservation):
    """Send email to admins about a new reservation request."""
    try:
        from django.core.mail import mail_admins
        subject = (
            f"Nouvelle demande de réservation — {reservation.full_name} "
            f"({reservation.vehicle})"
        )
        body = (
            f"Nouvelle demande de réservation sur {reservation.agency.name}\n\n"
            f"Client     : {reservation.full_name}\n"
            f"Téléphone  : {reservation.phone or '—'}\n"
            f"Email      : {reservation.email or '—'}\n"
            f"WhatsApp   : {reservation.whatsapp or '—'}\n\n"
            f"Véhicule   : {reservation.vehicle}\n"
            f"Dates      : {reservation.start_date} → {reservation.end_date}\n"
            f"Durée      : {reservation.duration_days} jour(s)\n"
            f"Message    : {reservation.message or '—'}\n\n"
            f"Connectez-vous au dashboard pour confirmer ou refuser."
        )
        mail_admins(subject, body, fail_silently=True)
    except Exception:
        pass


# ── CMS page detail ─────────────────────────────────────────────────

def page_detail(request: HttpRequest, slug: str, page_slug: str) -> HttpResponse:
    agency = _resolve_agency(slug, request)
    maintenance = _handle_maintenance(request, agency)
    if maintenance:
        return maintenance

    page = get_object_or_404(
        PublicPage.objects.for_agency(agency), slug=page_slug, is_published=True,
    )
    ctx = _theme_ctx(agency, request)
    ctx["page"] = page
    ctx["rendered_content"] = render_markdown(page.content)

    # Contact variant: inject agency contact info
    if page.template_variant == "contact":
        ss = _get_site_settings(agency)
        ctx["contact_phone"] = ss.contact_phone or getattr(agency, "public_phone", "")
        ctx["contact_email"] = ss.contact_email or agency.contact_email or ""
        ctx["contact_whatsapp"] = ss.whatsapp or getattr(agency, "public_whatsapp", "")
        ctx["contact_address"] = getattr(ss, "address", "") or getattr(agency, "public_address", "")
        ctx["contact_website"] = getattr(ss, "website", "") or ""

    # FAQ variant: parse ## headings into Q&A pairs
    if page.template_variant == "faq":
        faq_items = []
        current_q, current_a_lines = None, []
        for line in page.content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("## "):
                if current_q:
                    faq_items.append({"q": current_q, "a": render_markdown("\n".join(current_a_lines))})
                current_q = stripped[3:].strip()
                current_a_lines = []
            elif current_q is not None:
                current_a_lines.append(line)
        if current_q:
            faq_items.append({"q": current_q, "a": render_markdown("\n".join(current_a_lines))})
        ctx["faq_items"] = faq_items

    variant = page.template_variant
    VALID_VARIANTS = {"default", "about", "faq", "contact", "legal", "promo"}
    if variant not in VALID_VARIANTS:
        variant = "default"
    return render(request, f"public_site/page_{variant}.html", ctx)
