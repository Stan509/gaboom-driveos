import json
from datetime import date, timedelta
import base64
from decimal import Decimal

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from agencies.models import Agency, AgencySiteSection, AgencySiteSettings, BusinessSettings, DEFAULT_HOME_SECTIONS, MaintenanceRecord, ReservationRequest, Vehicle, has_date_conflict
from agencies.models_access import AgencyAccess, PaymentProof
from agencies.services import (
    PLAN_CONFIGS, apply_plan_to_access, get_agency_access,
    grant_bonus_days, renew_access, suspend_access, switch_to_paypal, sync_access,
)
from agencies.theme_presets import THEMES
from billing.models import Contract, Payment, VehicleReturnInspection, VehicleStatePhoto
from clients.models import Client, ClientNotification
from core.permissions import has_perm, require_perm
from core.models import User
from public_site.models import PublicPage

from .forms import (
    AccountProfileForm, AgencyProfileForm, AgencySiteSettingsForm,
    BusinessSettingsForm, ClientForm,
    ContractForm, MaintenanceRecordForm, PaymentForm, TeamMemberCreateForm,
    TeamMemberEditForm, UpdateKmForm, VehicleForm,
)


# ═══════════════════════════ helpers ═══════════════════════════════════

def _agency(request):
    return request.user.agency


def _is_admin(request):
    return request.user.role in ("agency_owner", "agency_manager")


def _has_perm(request, code):
    return has_perm(request.user, code)


# ═══════════════════════════ HOME ═════════════════════════════════════

@require_perm("dashboard.view")
def home(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    today = date.today()

    if request.session.get("_email_fail_open", False):
        messages.warning(
            request,
            "Email provider unavailable, user created (verification pending).",
        )

    # ── Base querysets (all scoped) ──────────────────────────────
    vehicles_qs = Vehicle.objects.for_agency(agency).select_related("agency")
    clients_qs = Client.objects.for_agency(agency)
    contracts_qs = Contract.objects.for_agency(agency)
    payments_qs = Payment.objects.for_agency(agency)

    vehicles_list = list(vehicles_qs)
    vehicles_count = len(vehicles_list)
    clients_count = clients_qs.count()
    active_contracts_count = contracts_qs.filter(status="active").count()
    team_count = agency.users.count()

    # ── KPI deltas (this month) ─────────────────────────────────
    month_start = today.replace(day=1)
    clients_new = clients_qs.filter(created_at__date__gte=month_start).count()
    contracts_new = contracts_qs.filter(created_at__date__gte=month_start).count()

    # ── Revenue chart ───────────────────────────────────────────
    range_days = int(request.GET.get("range", 30))
    if range_days not in (7, 30, 90):
        range_days = 30
    range_start = today - timedelta(days=range_days - 1)

    rev_by_day = dict(
        payments_qs.filter(
            status="succeeded",
            created_at__date__gte=range_start,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("amount"))
        .values_list("day", "total")
    )
    revenue_labels = []
    revenue_values = []
    for i in range(range_days):
        d = range_start + timedelta(days=i)
        revenue_labels.append(d.strftime("%d/%m"))
        revenue_values.append(float(rev_by_day.get(d, 0)))
    revenue_total = sum(revenue_values)

    # ── Contracts breakdown ─────────────────────────────────────
    contract_counts = dict(
        contracts_qs.values("status").annotate(n=Count("id")).values_list("status", "n")
    )
    chart_contracts = {
        "labels": ["Actifs", "Brouillons", "Clôturés"],
        "values": [
            contract_counts.get("active", 0),
            contract_counts.get("draft", 0),
            contract_counts.get("closed", 0),
        ],
    }

    # ── Fleet breakdown ─────────────────────────────────────────
    fleet = {"available": 0, "rented": 0, "maintenance": 0, "blocked": 0}
    for v in vehicles_list:
        ms = v.maintenance_status
        if ms == "blocked":
            fleet["blocked"] += 1
        elif v.status == "maintenance":
            fleet["maintenance"] += 1
        elif v.status == "rented":
            fleet["rented"] += 1
        else:
            fleet["available"] += 1

    # ── Alerts ──────────────────────────────────────────────────
    maint_alerts = []
    for v in vehicles_list:
        if v.maintenance_status in ("urgent", "blocked"):
            maint_alerts.append({
                "pk": v.pk, "label": f"{v.make} {v.model}",
                "plate": v.plate_number, "status": v.maintenance_status,
            })
    maint_alerts = maint_alerts[:5]

    license_alerts = list(
        clients_qs.exclude(driving_license_expiry__isnull=True)
        .order_by("driving_license_expiry")[:20]
    )
    license_alerts = [
        {"pk": c.pk, "label": c.full_name, "status": c.license_status}
        for c in license_alerts if c.license_status in ("expired",)
    ][:5]

    payment_alerts = list(
        contracts_qs.filter(payment_status__in=["unpaid", "partial"])
        .select_related("client")[:5]
    )

    # ── Recent activity (last 10 across entities) ───────────────
    activity = []
    for c in contracts_qs.select_related("client", "vehicle").order_by("-created_at")[:5]:
        activity.append({
            "type": "contract", "date": c.created_at,
            "text": f"Contrat #{c.pk} — {c.client.full_name}",
            "url": f"/dashboard/contracts/{c.pk}/",
        })
    for p in payments_qs.select_related("contract", "contract__client").order_by("-created_at")[:5]:
        activity.append({
            "type": "payment", "date": p.created_at,
            "text": f"Paiement {p.amount}{p.currency} — Contrat #{p.contract_id}",
            "url": f"/dashboard/contracts/{p.contract_id}/",
        })
    for cl in clients_qs.order_by("-created_at")[:5]:
        activity.append({
            "type": "client", "date": cl.created_at,
            "text": f"Client ajouté : {cl.full_name}",
            "url": f"/dashboard/clients/{cl.pk}/",
        })
    for mr in MaintenanceRecord.objects.filter(
        vehicle__agency=agency
    ).select_related("vehicle").order_by("-created_at")[:5]:
        activity.append({
            "type": "maintenance", "date": mr.created_at,
            "text": f"Entretien {mr.get_service_type_display()} — {mr.vehicle}",
            "url": f"/dashboard/maintenance/{mr.vehicle_id}/history/",
        })
    activity.sort(key=lambda a: a["date"], reverse=True)
    activity = activity[:10]

    return render(request, "dashboard/home.html", {
        "page_id": "home",
        "agency": agency,
        # KPIs
        "vehicles_count": vehicles_count,
        "clients_count": clients_count,
        "active_contracts_count": active_contracts_count,
        "team_count": team_count,
        "clients_new": clients_new,
        "contracts_new": contracts_new,
        # Charts (JSON for JS)
        "chart_revenue_json": json.dumps({
            "labels": revenue_labels, "values": revenue_values,
        }),
        "revenue_total": revenue_total,
        "range_days": range_days,
        "chart_contracts_json": json.dumps(chart_contracts),
        # Fleet
        "fleet": fleet,
        "fleet_total": vehicles_count,
        # Alerts
        "maint_alerts": maint_alerts,
        "license_alerts": license_alerts,
        "payment_alerts": payment_alerts,
        # Activity
        "activity": activity,
    })


# ═══════════════════════════ VEHICLES ═════════════════════════════════

@require_perm("vehicles.view")
def vehicle_hub(request: HttpRequest) -> HttpResponse:
    """Single-page vehicle list + create/edit form (query param ?edit=<id>)."""
    agency = _agency(request)
    can_create = _has_perm(request, "vehicles.create") or _is_admin(request)
    can_update = _has_perm(request, "vehicles.edit") or _is_admin(request)
    can_edit = can_create or can_update

    # ── Filters ──────────────────────────────────────────────────
    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "")
    visible_f = request.GET.get("visible", "")
    sort_by = request.GET.get("sort", "name")
    edit_pk = request.GET.get("edit", "")

    qs = Vehicle.objects.for_agency(agency).select_related("agency")
    if q:
        qs = qs.filter(
            Q(make__icontains=q) | Q(model__icontains=q) | Q(plate_number__icontains=q)
        )
    if status_f:
        qs = qs.filter(status=status_f)
    if visible_f == "1":
        qs = qs.filter(public_visible=True)
    elif visible_f == "0":
        qs = qs.filter(public_visible=False)

    if sort_by == "price":
        qs = qs.order_by("daily_price")
    elif sort_by == "km":
        qs = qs.order_by("-current_km")
    elif sort_by == "status":
        qs = qs.order_by("status", "make")
    else:
        qs = qs.order_by("make", "model")

    vehicles_all = list(qs)

    # ── Pagination ────────────────────────────────────────────────
    page_num = int(request.GET.get("page", 1) or 1)
    per_page = 30
    total_pages = max((len(vehicles_all) + per_page - 1) // per_page, 1)
    page_num = max(1, min(page_num, total_pages))
    start = (page_num - 1) * per_page
    vehicles = vehicles_all[start:start + per_page]

    # ── Quick stats (DB-level) ────────────────────────────────────
    stats_qs = Vehicle.objects.for_agency(agency)
    stats = {
        "available": stats_qs.filter(status="available").count(),
        "maintenance": sum(1 for v in vehicles_all if v.maintenance_status in ("urgent", "blocked")),
        "hidden": stats_qs.filter(public_visible=False).count(),
    }

    # ── Form (create or edit) ────────────────────────────────────
    editing = None
    if edit_pk:
        try:
            editing = Vehicle.objects.for_agency(agency).select_related("agency").get(pk=int(edit_pk))
        except (Vehicle.DoesNotExist, ValueError):
            editing = None

    if request.method == "POST" and can_edit:
        vehicle_id = request.POST.get("vehicle_id", "").strip()
        if vehicle_id:
            if not can_update:
                return HttpResponseForbidden()
            instance = get_object_or_404(Vehicle.objects.for_agency(agency), pk=int(vehicle_id))
            form = VehicleForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                form.save()
                messages.success(request, "Véhicule mis à jour.")
                return redirect(f"/dashboard/vehicles/?edit={instance.pk}&{_qs_keep(request)}")
        else:
            if not can_create:
                return HttpResponseForbidden()
            form = VehicleForm(request.POST, request.FILES)
            if form.is_valid():
                access = get_agency_access(agency)
                if access.max_vehicles and agency.vehicles.count() >= access.max_vehicles:
                    form.add_error(None, "Limite de véhicules atteinte pour votre plan.")
                else:
                    v = form.save(commit=False)
                    v.agency = agency
                    v.save()
                    messages.success(request, "Véhicule ajouté.")
                    return redirect(f"/dashboard/vehicles/?{_qs_keep(request)}")
    else:
        form = VehicleForm(instance=editing) if editing else VehicleForm()

    # Smart pricing recommendation
    smart_pricing = None
    if editing:
        from dashboard.services import compute_recommended_price
        smart_pricing = compute_recommended_price(editing)

    # Get plan features safely
    plan_features = {}
    try:
        plan_features = get_agency_access(agency).plan_features
    except Exception:
        plan_features = {}

    return render(request, "dashboard/vehicles/hub.html", {
        "page_id": "vehicles", "breadcrumb": "Véhicules",
        "vehicles": vehicles, "can_edit": can_edit,
        "form": form, "editing": editing,
        "q": q, "status_filter": status_f, "visible_filter": visible_f,
        "sort_by": sort_by, "stats": stats,
        "smart_pricing": smart_pricing,
        "page_num": page_num, "total_pages": total_pages,
        "has_prev": page_num > 1, "has_next": page_num < total_pages,
        "total_count": len(vehicles_all),
        "plan_features": plan_features,
    })


def _qs_keep(request):
    """Preserve filter query string across redirects."""
    parts = []
    for k in ("q", "status", "visible", "sort"):
        v = request.GET.get(k, "")
        if v:
            parts.append(f"{k}={v}")
    return "&".join(parts)


@require_perm("vehicles.view")
def vehicle_list(request: HttpRequest) -> HttpResponse:
    """Legacy redirect → hub."""
    return redirect("dashboard:vehicle_hub")


@require_perm("vehicles.create")
def vehicle_create(request: HttpRequest) -> HttpResponse:
    """Legacy redirect → hub (create mode)."""
    return redirect("dashboard:vehicle_hub")


@require_perm("vehicles.edit")
def vehicle_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Legacy redirect → hub (edit mode)."""
    return redirect(f"/dashboard/vehicles/?edit={pk}")


@require_perm("vehicles.delete")
def vehicle_delete(request: HttpRequest, pk: int) -> HttpResponse:
    vehicle = get_object_or_404(Vehicle.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST":
        vehicle.delete()
        messages.success(request, "Véhicule supprimé.")
        return redirect("dashboard:vehicle_hub")
    return render(request, "dashboard/vehicles/confirm_delete.html", {
        "page_id": "vehicles", "breadcrumb": "Véhicules", "vehicle": vehicle,
    })


@require_perm("vehicles.create")
def vehicle_duplicate(request: HttpRequest, pk: int) -> HttpResponse:
    """Clone a vehicle (without image). POST only."""
    if request.method != "POST":
        return redirect("dashboard:vehicle_hub")
    src = get_object_or_404(Vehicle.objects.for_agency(_agency(request)), pk=pk)
    access = get_agency_access(src.agency)
    if access.max_vehicles and src.agency.vehicles.count() >= access.max_vehicles:
        messages.error(request, "Limite de véhicules atteinte pour votre plan.")
        return redirect("dashboard:vehicle_hub")
    src.pk = None
    src.image = None
    src.plate_number = f"{src.plate_number}-COPIE"
    src.save()
    messages.success(request, f"Véhicule dupliqué : {src.make} {src.model}.")
    return redirect(f"/dashboard/vehicles/?edit={src.pk}")


@require_perm("vehicles.edit")
def vehicle_toggle_negotiation(request: HttpRequest, pk: int) -> HttpResponse:
    """Toggle allow_negotiation on a vehicle. POST only."""
    if request.method != "POST":
        return HttpResponseForbidden()
    vehicle = get_object_or_404(Vehicle.objects.for_agency(_agency(request)), pk=pk)
    vehicle.allow_negotiation = not vehicle.allow_negotiation
    vehicle.save(update_fields=["allow_negotiation"])
    status = "activée" if vehicle.allow_negotiation else "désactivée"
    messages.success(request, f"Négociation {status} pour {vehicle}.")
    return redirect(f"/dashboard/vehicles/?{_qs_keep(request)}")


# ═══════════════════════════ CLIENTS ══════════════════════════════════

def _client_qs_keep(request):
    """Preserve client filter query string across redirects."""
    parts = []
    for k in ("q", "status", "license", "sort"):
        v = request.GET.get(k, "")
        if v:
            parts.append(f"{k}={v}")
    return "&".join(parts)


def _days_until_expiry(client):
    """Return days until license expiry, or None if missing."""
    if not client.driving_license_expiry:
        return None
    return (client.driving_license_expiry - date.today()).days


@require_perm("clients.view")
def client_hub(request: HttpRequest) -> HttpResponse:
    """Single-page client list + create/edit form (query param ?edit=<id>)."""
    agency = _agency(request)
    can_create = _has_perm(request, "clients.create") or _is_admin(request)
    can_update = _has_perm(request, "clients.edit") or _is_admin(request)
    can_edit = can_create or can_update

    # ── Filters ──────────────────────────────────────────────────
    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "")
    license_f = request.GET.get("license", "")
    sort_by = request.GET.get("sort", "name")
    edit_pk = request.GET.get("edit", "")

    qs = Client.objects.for_agency(agency)
    if q:
        qs = qs.filter(
            Q(full_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
        )
    if status_f:
        qs = qs.filter(status=status_f)

    if sort_by == "date":
        qs = qs.order_by("-created_at")
    elif sort_by == "expiry":
        qs = qs.order_by("driving_license_expiry")
    else:
        qs = qs.order_by("full_name")

    clients_all = list(qs)
    if license_f:
        clients_all = [c for c in clients_all if c.license_status == license_f]

    # Annotate days_until_expiry on each client for template use
    for c in clients_all:
        c.days_left = _days_until_expiry(c)

    # ── Pagination ────────────────────────────────────────────────
    page_num = int(request.GET.get("page", 1) or 1)
    per_page = 30
    total_pages = max((len(clients_all) + per_page - 1) // per_page, 1)
    page_num = max(1, min(page_num, total_pages))
    start = (page_num - 1) * per_page
    clients = clients_all[start:start + per_page]

    # ── KPIs (DB-level counts to avoid loading all clients) ─────
    all_qs = Client.objects.for_agency(agency)
    today = date.today()
    kpi = {
        "total": all_qs.count(),
        "valid": all_qs.filter(driving_license_expiry__gt=today).count(),
        "expired": all_qs.filter(driving_license_expiry__lte=today).count(),
        "missing": all_qs.filter(driving_license_expiry__isnull=True).count(),
    }

    # ── Form (create or edit) ────────────────────────────────────
    editing = None
    if edit_pk:
        try:
            editing = Client.objects.for_agency(agency).get(pk=int(edit_pk))
        except (Client.DoesNotExist, ValueError):
            editing = None

    if request.method == "POST" and can_edit:
        client_id = request.POST.get("client_id", "").strip()
        if client_id:
            if not can_update:
                return HttpResponseForbidden()
            instance = get_object_or_404(Client.objects.for_agency(agency), pk=int(client_id))
            form = ClientForm(request.POST, request.FILES, instance=instance)
            if form.is_valid():
                form.save()
                messages.success(request, "Client mis à jour.")
                return redirect(f"/dashboard/clients/?edit={instance.pk}&{_client_qs_keep(request)}")
        else:
            if not can_create:
                return HttpResponseForbidden()
            form = ClientForm(request.POST, request.FILES)
            if form.is_valid():
                c = form.save(commit=False)
                c.agency = agency
                c.save()
                messages.success(request, "Client ajouté.")
                return redirect(f"/dashboard/clients/?{_client_qs_keep(request)}")
    else:
        form = ClientForm(instance=editing) if editing else ClientForm()

    return render(request, "dashboard/clients/hub.html", {
        "page_id": "clients", "breadcrumb": "Clients",
        "clients": clients, "can_edit": can_edit,
        "form": form, "editing": editing,
        "q": q, "status_filter": status_f, "license_filter": license_f,
        "sort_by": sort_by, "kpi": kpi,
        "page_num": page_num, "total_pages": total_pages,
        "has_prev": page_num > 1, "has_next": page_num < total_pages,
        "total_count": len(clients_all),
    })


@require_perm("clients.view")
def client_list(request: HttpRequest) -> HttpResponse:
    """Legacy redirect → hub."""
    return redirect("dashboard:client_hub")


@require_perm("clients.create")
def client_create(request: HttpRequest) -> HttpResponse:
    """Legacy redirect → hub."""
    return redirect("dashboard:client_hub")


@require_perm("clients.edit")
def client_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Legacy redirect → hub (edit mode)."""
    return redirect(f"/dashboard/clients/?edit={pk}")


@require_perm("clients.view")
def client_detail(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    client = get_object_or_404(Client.objects.for_agency(agency), pk=pk)
    contracts = Contract.objects.for_agency(agency).filter(client=client).select_related("vehicle")
    total_paid = contracts.aggregate(t=Sum("amount_paid"))["t"] or 0
    days_left = _days_until_expiry(client)
    return render(request, "dashboard/clients/detail.html", {
        "page_id": "clients", "breadcrumb": "Clients",
        "client": client, "contracts": contracts,
        "total_contracts": contracts.count(),
        "total_paid": total_paid,
        "last_contract": contracts.first(),
        "can_edit": _is_admin(request),
        "days_left": days_left,
    })


@require_perm("clients.delete")
def client_delete(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(Client.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST":
        client.delete()
        messages.success(request, "Client supprimé.")
        return redirect("dashboard:client_hub")
    return render(request, "dashboard/clients/confirm_delete.html", {
        "page_id": "clients", "breadcrumb": "Clients", "client": client,
    })


# ═══════════════════════════ CONTRACTS ════════════════════════════════

def _contract_qs_keep(request):
    """Preserve contract filter query string across redirects."""
    parts = []
    for k in ("q", "status", "pay", "sort"):
        v = request.GET.get(k, "")
        if v:
            parts.append(f"{k}={v}")
    return "&".join(parts)


@require_perm("contracts.view")
def contract_hub(request: HttpRequest) -> HttpResponse:
    """Single-page contract list + create/edit form (query param ?edit=<id>)."""
    agency = _agency(request)
    can_edit = _is_admin(request)
    today = date.today()

    # ── Filters ──────────────────────────────────────────────────
    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "")
    pay_f = request.GET.get("pay", "")
    sort_by = request.GET.get("sort", "date")
    edit_pk = request.GET.get("edit", "")

    qs = Contract.objects.for_agency(agency).select_related("client", "vehicle")
    if q:
        qs = qs.filter(
            Q(client__full_name__icontains=q)
            | Q(vehicle__make__icontains=q)
            | Q(vehicle__model__icontains=q)
            | Q(vehicle__plate_number__icontains=q)
        )
    if status_f:
        qs = qs.filter(status=status_f)
    if pay_f:
        qs = qs.filter(payment_status=pay_f)

    if sort_by == "amount":
        qs = qs.order_by("-montant_ttc")
    elif sort_by == "due":
        qs = qs.order_by("-amount_due")
    elif sort_by == "start":
        qs = qs.order_by("-start_date")
    else:
        qs = qs.order_by("-created_at")

    contracts_all = list(qs)

    # Annotate is_overdue on each contract
    for c in contracts_all:
        c.is_overdue = c.status == "active" and c.end_date < today

    payments_qs = Payment.objects.for_agency(agency).select_related(
        "contract", "contract__client", "contract__vehicle", "created_by"
    )
    if q:
        payments_qs = payments_qs.filter(
            Q(contract__client__full_name__icontains=q)
            | Q(contract__vehicle__make__icontains=q)
            | Q(contract__vehicle__model__icontains=q)
            | Q(contract__vehicle__plate_number__icontains=q)
            | Q(reference__icontains=q)
            | Q(contract__pk__icontains=q)
        )
    if status_f:
        payments_qs = payments_qs.filter(contract__status=status_f)
    if pay_f:
        payments_qs = payments_qs.filter(contract__payment_status=pay_f)
    payments_all = list(payments_qs)

    entries = []
    for c in contracts_all:
        entries.append({
            "type": "contract",
            "contract": c,
            "date": c.created_at,
            "amount": c.montant_ttc,
            "due": c.amount_due,
            "start": c.start_date,
        })
    for p in payments_all:
        entries.append({
            "type": "payment",
            "payment": p,
            "date": p.created_at,
            "amount": p.amount,
            "due": Decimal(0),
            "start": p.created_at.date(),
        })

    if sort_by == "amount":
        entries.sort(key=lambda e: e["amount"], reverse=True)
    elif sort_by == "due":
        entries.sort(key=lambda e: e["due"], reverse=True)
    elif sort_by == "start":
        entries.sort(key=lambda e: e["start"], reverse=True)
    else:
        entries.sort(key=lambda e: e["date"], reverse=True)

    # ── Pagination ────────────────────────────────────────────────
    page_num = int(request.GET.get("page", 1) or 1)
    per_page = 30
    total_pages = max((len(entries) + per_page - 1) // per_page, 1)
    page_num = max(1, min(page_num, total_pages))
    start = (page_num - 1) * per_page
    page_entries = entries[start:start + per_page]

    # ── KPIs ─────────────────────────────────────────────────────
    all_qs = Contract.objects.for_agency(agency)
    kpi = {
        "active": all_qs.filter(status="active").count(),
        "to_collect": all_qs.filter(amount_due__gt=0, status__in=("active", "closed")).count(),
        "today": all_qs.filter(start_date=today).count(),
        "closed_30d": all_qs.filter(
            status="closed", closed_at__date__gte=today - timedelta(days=30)
        ).count(),
    }

    # ── Payments tab ─────────────────────────────────────────────
    payment_qs, payment_filters = _payment_filtered_qs(request, prefix="p_")
    payments_all = list(payment_qs)

    succeeded_qs = [p for p in payments_all if p.status == "succeeded"]
    total_collected = sum(p.amount for p in succeeded_qs)
    today_collected = sum(
        p.amount for p in succeeded_qs
        if p.created_at.date() == today
    )
    payment_count = len(payments_all)

    method_counts = {}
    for p in succeeded_qs:
        method_counts[p.method] = method_counts.get(p.method, 0) + 1
    dominant_method = max(method_counts, key=method_counts.get) if method_counts else None
    METHOD_LABELS = {
        "cash": _("Espèces"),
        "card_terminal": _("Terminal CB"),
        "bank_transfer": _("Virement"),
    }
    dominant_label = METHOD_LABELS.get(dominant_method, "-") if dominant_method else "-"

    payment_kpi = {
        "total_collected": total_collected,
        "today_collected": today_collected,
        "count": payment_count,
        "dominant_method": dominant_label,
    }

    payment_page_num = int(request.GET.get("p_page", 1) or 1)
    payment_per_page = 25
    payment_total_pages = max((len(payments_all) + payment_per_page - 1) // payment_per_page, 1)
    payment_page_num = max(1, min(payment_page_num, payment_total_pages))
    payment_start = (payment_page_num - 1) * payment_per_page
    payment_page = payments_all[payment_start:payment_start + payment_per_page]

    tab = request.GET.get("tab", "contracts")
    if tab not in ("contracts", "payments"):
        tab = "contracts"

    # ── Form (create or edit) ────────────────────────────────────
    editing = None
    if edit_pk:
        try:
            editing = Contract.objects.for_agency(agency).select_related(
                "client", "vehicle"
            ).get(pk=int(edit_pk))
        except (Contract.DoesNotExist, ValueError):
            editing = None

    pay_form = PaymentForm()

    if request.method == "POST" and can_edit:
        contract_id = request.POST.get("contract_id", "").strip()
        if contract_id:
            instance = get_object_or_404(
                Contract.objects.for_agency(agency), pk=int(contract_id)
            )
            form = ContractForm(request.POST, instance=instance, agency=agency)
            if form.is_valid():
                obj = form.save(commit=False)
                # If vehicle changed, check the new vehicle isn't occupied
                if obj.vehicle_id and obj.vehicle_id != instance.vehicle_id:
                    existing = Contract.vehicle_has_active_contract(obj.vehicle, exclude_pk=obj.pk)
                    if existing:
                        messages.error(
                            request,
                            _(
                                "Ce véhicule est déjà lié au contrat #%(pk)s (%(status)s). "
                                "Clôturez ou annulez-le d'abord."
                            )
                            % {"pk": existing.pk, "status": existing.get_status_display()},
                        )
                        return redirect(f"/dashboard/contracts/?edit={instance.pk}&{_contract_qs_keep(request)}")
                obj.save()
                form.save_m2m()
                messages.success(request, _("Contrat mis à jour."))
                return redirect(
                    f"/dashboard/contracts/?edit={instance.pk}&{_contract_qs_keep(request)}"
                )
        else:
            form = ContractForm(request.POST, agency=agency)
            pay_form = PaymentForm(request.POST)
            if form.is_valid() and pay_form.is_valid():
                amount = pay_form.cleaned_data.get("amount") or Decimal(0)
                if amount <= 0:
                    pay_form.add_error("amount", _("Montant requis."))
                else:
                    c = form.save(commit=False)
                    c.agency = agency
                    # Block if vehicle already has an active contract
                    existing = Contract.vehicle_has_active_contract(c.vehicle)
                    if existing:
                        messages.error(
                            request,
                            _(
                                "Ce véhicule est déjà lié au contrat #%(pk)s (%(status)s). "
                                "Clôturez ou annulez-le d'abord."
                            )
                            % {"pk": existing.pk, "status": existing.get_status_display()},
                        )
                        return redirect(f"/dashboard/contracts/?{_contract_qs_keep(request)}")
                    c.vat_percent = agency.vat_percent
                    c.currency = agency.currency
                    # Compute initial totals
                    c.subtotal_ht = Decimal(c.nb_days) * c.price_per_day
                    c.montant_ttc = c.subtotal_ht
                    c.amount_due = c.montant_ttc
                    c.save()
                    # Auto-set vehicle status to "rented" when contract is active
                    if c.vehicle and c.vehicle.status == "available" and c.status == "active":
                        c.vehicle.status = "rented"
                        c.vehicle.save(update_fields=["status"])
                    p = pay_form.save(commit=False)
                    p.agency = agency
                    p.contract = c
                    p.created_by = request.user
                    p.currency = c.currency
                    p.save()
                    c.recalc_payments()
                    c.save(update_fields=["amount_paid", "amount_due", "payment_status"])
                    messages.success(request, _("Contrat et paiement enregistrés."))
                    return redirect(
                        f"/dashboard/contracts/?{request.META.get('QUERY_STRING', '')}"
                    )
    else:
        form = ContractForm(instance=editing, agency=agency) if editing else ContractForm(agency=agency)

    return render(request, "dashboard/contracts/hub.html", {
        "page_id": "contracts", "breadcrumb": "Contrat et Paiement",
        "entries": page_entries, "can_edit": can_edit,
        "form": form, "editing": editing,
        "q": q, "status_filter": status_f, "pay_filter": pay_f,
        "sort_by": sort_by, "kpi": kpi,
        "pay_form": pay_form,
        "page_num": page_num, "total_pages": total_pages,
        "has_prev": page_num > 1, "has_next": page_num < total_pages,
        "total_count": len(entries),
        "payment_entries": payment_page,
        "payment_kpi": payment_kpi,
        "payment_filters": payment_filters,
        "payment_page_num": payment_page_num,
        "payment_total_pages": payment_total_pages,
        "payment_has_prev": payment_page_num > 1,
        "payment_has_next": payment_page_num < payment_total_pages,
        "payment_total_count": len(payments_all),
        "tab": tab,
    })


@require_perm("contracts.view")
def contract_list(request: HttpRequest) -> HttpResponse:
    """Legacy redirect → hub."""
    return redirect("dashboard:contract_hub")


@require_perm("contracts.create")
def contract_create(request: HttpRequest) -> HttpResponse:
    """Legacy redirect → hub."""
    return redirect("dashboard:contract_hub")


@require_perm("contracts.view")
def contract_detail(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    contract = get_object_or_404(
        Contract.objects.for_agency(agency).select_related("client", "vehicle", "reservation"), pk=pk
    )
    payments = contract.payments.all()
    pay_form = PaymentForm(initial={"currency": contract.currency})
    today = date.today()
    is_overdue = contract.status == "active" and contract.end_date < today
    days_remaining = (contract.end_date - today).days if contract.status == "active" else None
    pickup_photos = contract.vehicle_photos.filter(moment="pickup")
    return_photos = contract.vehicle_photos.filter(moment="return")
    inspection = getattr(contract, 'return_inspection', None)
    return render(request, "dashboard/contracts/detail.html", {
        "page_id": "contracts", "breadcrumb": "Contrats",
        "contract": contract, "payments": payments,
        "pay_form": pay_form, "can_edit": _is_admin(request),
        "is_overdue": is_overdue, "days_remaining": days_remaining,
        "pickup_photos": pickup_photos, "return_photos": return_photos,
        "inspection": inspection,
    })


@require_perm("contracts.edit")
def contract_sign_client(request: HttpRequest, pk: int) -> HttpResponse:
    """Admin-side: capture the client's signature from the dashboard (canvas → base64 image)."""
    if request.method != "POST":
        return redirect("dashboard:contract_detail", pk=pk)

    agency = _agency(request)
    contract = get_object_or_404(Contract.objects.for_agency(agency), pk=pk)

    sig_data = request.POST.get("signature", "")
    if not sig_data or "base64," not in sig_data:
        messages.error(request, "Veuillez dessiner la signature du client.")
        return redirect("dashboard:contract_detail", pk=pk)

    fmt, imgstr = sig_data.split(";base64,")
    ext = fmt.split("/")[-1]
    if ext not in ("png", "jpeg", "webp"):
        ext = "png"

    file_name = f"sig_contract_{contract.pk}_admin.{ext}"
    sig_file = ContentFile(base64.b64decode(imgstr), name=file_name)

    contract.client_signature = sig_file
    contract.client_signed_at = timezone.now()
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        contract.client_signed_ip = x_forwarded.split(",")[0].strip()
    else:
        contract.client_signed_ip = request.META.get("REMOTE_ADDR")
    contract.save(update_fields=[
        "client_signature", "client_signed_at", "client_signed_ip",
    ])

    messages.success(request, "Signature client enregistrée.")
    return redirect("dashboard:contract_detail", pk=pk)


@require_perm("contracts.edit")
def contract_close(request: HttpRequest, pk: int) -> HttpResponse:
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST" and contract.status not in ("closed", "cancelled"):
        contract.km_retour = int(request.POST.get("km_retour", 0) or 0)
        contract.fuel_retour = int(request.POST.get("fuel_retour", 0) or 0)
        contract.frais_degats = int(request.POST.get("frais_degats", 0) or 0)
        contract.compute_close()
        contract.save()
        if contract.vehicle:
            contract.vehicle.current_km = contract.km_retour or contract.vehicle.current_km
            contract.vehicle.status = "available"
            contract.vehicle.gps_enabled = False
            contract.vehicle.save(update_fields=["current_km", "status", "gps_enabled"])
        messages.success(request, "Contrat clôturé.")
        return redirect("dashboard:contract_detail", pk=pk)
    return render(request, "dashboard/contracts/close.html", {
        "page_id": "contracts", "breadcrumb": "Contrats", "contract": contract,
    })


@require_perm("contracts.edit")
def contract_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """Cancel a contract (POST only)."""
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST" and contract.status in ("draft", "active"):
        contract.status = "cancelled"
        contract.save(update_fields=["status"])
        if contract.vehicle and contract.vehicle.status == "rented":
            contract.vehicle.status = "available"
            contract.vehicle.gps_enabled = False
            contract.vehicle.save(update_fields=["status", "gps_enabled"])
        messages.success(request, "Contrat annulé.")
    return redirect("dashboard:contract_detail", pk=pk)


@require_perm("contracts.edit")
def contract_send_to_sign(request: HttpRequest, pk: int) -> HttpResponse:
    """Move contract from draft → pending_signature."""
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST" and contract.status == "draft":
        contract.status = "pending_signature"
        contract.save(update_fields=["status"])
        # Notify client if linked
        if contract.client_account:
            ClientNotification.objects.create(
                client=contract.client_account,
                title="Contrat à signer",
                message=f"Un contrat #{contract.pk} pour le véhicule {contract.vehicle} est prêt à être signé. Rendez-vous dans votre espace client, section Mes contrats.",
                notif_type="info",
            )
        messages.success(request, "Contrat envoyé au client pour signature.")
    return redirect("dashboard:contract_detail", pk=pk)


@require_perm("contracts.edit")
def contract_activate(request: HttpRequest, pk: int) -> HttpResponse:
    """Activate a signed contract (pending_signature → active). Vehicle → rented."""
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST" and contract.status in ("draft", "pending_signature"):
        # Block if another active contract already occupies this vehicle
        if contract.vehicle:
            existing = Contract.vehicle_has_active_contract(contract.vehicle, exclude_pk=contract.pk)
            if existing and existing.status == "active":
                messages.error(
                    request,
                    f"Le véhicule {contract.vehicle} est déjà en location "
                    f"(contrat #{existing.pk}). Clôturez ou annulez-le d'abord.",
                )
                return redirect("dashboard:contract_detail", pk=pk)
        contract.status = "active"
        if not contract.pickup_datetime:
            contract.pickup_datetime = timezone.now()
        contract.save(update_fields=["status", "pickup_datetime"])
        if contract.vehicle:
            contract.vehicle.status = "rented"
            # Enable GPS tracking if vehicle has a GPS device configured
            gps_fields = ["status"]
            if contract.vehicle.gps_imei or contract.vehicle.gps_ip:
                contract.vehicle.gps_enabled = True
                gps_fields.append("gps_enabled")
            contract.vehicle.save(update_fields=gps_fields)
        messages.success(request, "Contrat activé — véhicule en location.")
    return redirect("dashboard:contract_detail", pk=pk)


@require_perm("contracts.edit")
def contract_start_return(request: HttpRequest, pk: int) -> HttpResponse:
    """Move contract to pending_return status."""
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST" and contract.status == "active":
        contract.status = "pending_return"
        contract.actual_return_datetime = timezone.now()
        contract.save(update_fields=["status", "actual_return_datetime"])
        messages.success(request, "Retour du véhicule initié — procédez à l'inspection.")
    return redirect("dashboard:contract_inspection", pk=pk)


@require_perm("contracts.edit")
def contract_inspection(request: HttpRequest, pk: int) -> HttpResponse:
    """Vehicle return inspection form."""
    agency = _agency(request)
    contract = get_object_or_404(
        Contract.objects.for_agency(agency).select_related("client", "vehicle"), pk=pk,
    )
    inspection = getattr(contract, 'return_inspection', None)
    pickup_photos = contract.vehicle_photos.filter(moment="pickup")
    return_photos = contract.vehicle_photos.filter(moment="return")

    if request.method == "POST":
        # Create or update inspection
        if not inspection:
            inspection = VehicleReturnInspection(contract=contract, inspected_by=request.user)

        inspection.exterior_condition = request.POST.get("exterior_condition", "good")
        inspection.interior_condition = request.POST.get("interior_condition", "good")
        inspection.tires_condition = request.POST.get("tires_condition", "good")
        inspection.lights_condition = request.POST.get("lights_condition", "good")
        inspection.engine_condition = request.POST.get("engine_condition", "good")
        inspection.has_new_damage = request.POST.get("has_new_damage") == "1"
        inspection.damage_description = request.POST.get("damage_description", "").strip()[:2000]
        try:
            inspection.damage_cost_estimate = Decimal(request.POST.get("damage_cost_estimate", "0") or "0")
        except Exception:
            inspection.damage_cost_estimate = Decimal(0)
        inspection.cleanliness_ok = request.POST.get("cleanliness_ok") == "1"
        inspection.notes = request.POST.get("notes", "").strip()[:2000]
        inspection.decision = request.POST.get("decision", "available")
        inspection.save()

        # Update contract return data
        contract.km_retour = int(request.POST.get("km_retour", 0) or 0)
        contract.fuel_retour = int(request.POST.get("fuel_retour", 0) or 0)
        contract.frais_degats = inspection.damage_cost_estimate

        # Compute and close
        contract.compute_close()
        contract.save()

        # Update vehicle status based on inspection decision
        if contract.vehicle:
            contract.vehicle.current_km = contract.km_retour or contract.vehicle.current_km
            if inspection.decision == "maintenance":
                contract.vehicle.status = "maintenance"
            else:
                contract.vehicle.status = "available"
            contract.vehicle.gps_enabled = False
            contract.vehicle.save(update_fields=["current_km", "status", "gps_enabled"])

        messages.success(request, "Inspection terminée — contrat clôturé.")
        return redirect("dashboard:contract_detail", pk=pk)

    return render(request, "dashboard/contracts/inspection.html", {
        "page_id": "contracts", "breadcrumb": "Contrats",
        "contract": contract, "inspection": inspection,
        "pickup_photos": pickup_photos, "return_photos": return_photos,
        "condition_choices": VehicleReturnInspection.CONDITION_CHOICES,
        "decision_choices": VehicleReturnInspection.DECISION_CHOICES,
    })


@require_perm("contracts.edit")
def contract_photo_upload(request: HttpRequest, pk: int) -> HttpResponse:
    """Upload vehicle state photos (pickup or return)."""
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST":
        moment = request.POST.get("moment", "pickup")
        if moment not in ("pickup", "return"):
            moment = "pickup"
        description = request.POST.get("description", "").strip()[:255]
        photos = request.FILES.getlist("photos")
        for photo in photos[:10]:  # max 10 at a time
            if photo.size > 10 * 1024 * 1024:
                continue
            VehicleStatePhoto.objects.create(
                contract=contract, moment=moment,
                photo=photo, description=description,
            )
        messages.success(request, f"{len(photos)} photo(s) ajoutée(s).")
        next_url = request.POST.get("next", "")
        if next_url:
            return redirect(next_url)
    return redirect("dashboard:contract_detail", pk=pk)


@require_perm("contracts.edit")
def contract_photo_delete(request: HttpRequest, pk: int, photo_pk: int) -> HttpResponse:
    """Delete a vehicle state photo."""
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=pk)
    photo = get_object_or_404(VehicleStatePhoto, pk=photo_pk, contract=contract)
    if request.method == "POST":
        photo.photo.delete(save=False)
        photo.delete()
        messages.success(request, "Photo supprimée.")
    next_url = request.POST.get("next", "") if request.method == "POST" else ""
    if next_url:
        return redirect(next_url)
    return redirect("dashboard:contract_detail", pk=pk)


@require_perm("contracts.create")
def contract_from_reservation(request: HttpRequest, reservation_pk: int) -> HttpResponse:
    """Create a contract pre-filled from a confirmed reservation."""
    agency = _agency(request)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency), pk=reservation_pk,
    )
    # Check if contract already exists for this reservation
    if hasattr(reservation, 'contract') and reservation.contract:
        messages.info(request, "Un contrat existe déjà pour cette réservation.")
        return redirect("dashboard:contract_detail", pk=reservation.contract.pk)

    # Block if vehicle already has an active contract
    existing = Contract.vehicle_has_active_contract(reservation.vehicle)
    if existing:
        messages.error(
            request,
            f"Le véhicule {reservation.vehicle} est déjà lié au contrat #{existing.pk} "
            f"({existing.get_status_display()}). "
            f"Clôturez ou annulez ce contrat avant d'en créer un nouveau.",
        )
        return redirect("dashboard:reservation_detail", pk=reservation_pk)

    # Find or create client
    client_qs = Client.objects.for_agency(agency)
    client = None
    if reservation.phone:
        client = client_qs.filter(phone=reservation.phone).first()
    if not client and reservation.email:
        client = client_qs.filter(email=reservation.email).first()
    if not client:
        client = Client.objects.create(
            agency=agency,
            full_name=reservation.full_name or reservation.email or reservation.phone,
            phone=reservation.phone,
            email=reservation.email,
        )

    # Determine price
    price = reservation.daily_price_accepted or reservation.daily_price_official or reservation.vehicle.daily_price

    # Pre-fill contract clause from agency settings
    clause = ""
    penalty = ""
    gps_clause_text = ""
    try:
        bs = agency.business_settings
        clause = bs.default_contract_clause
        penalty = bs.default_penalty_clause
        # Add GPS clause if vehicle has GPS configured
        if (reservation.vehicle.gps_imei or reservation.vehicle.gps_ip) and bs.default_gps_clause:
            gps_clause_text = bs.default_gps_clause
    except Exception:
        pass

    contract = Contract.objects.create(
        agency=agency,
        client=client,
        client_account=reservation.client_account,
        vehicle=reservation.vehicle,
        reservation=reservation,
        start_date=reservation.start_date,
        end_date=reservation.end_date,
        price_per_day=price,
        contract_clause=clause,
        penalty_clause=penalty,
        gps_clause=gps_clause_text,
        status="draft",
    )
    # Pre-fill defaults from BusinessSettings
    try:
        bs = agency.business_settings
        contract.km_included = bs.km_included or 200
        contract.km_price = bs.km_extra_price or Decimal("0.30")
        contract.fuel_fee = bs.fuel_fee or Decimal("30.00")
        contract.late_fee = bs.late_fee_per_day or Decimal("50.00")
        contract.deposit = bs.deposit_default or Decimal("0")
        contract.vat_percent = bs.vat_percent or Decimal("0")
        contract.currency = bs.currency or "EUR"
        contract.save()
    except Exception:
        pass

    # Mark reservation as "contracted" — it's no longer just a reservation
    reservation.status = "contracted"
    reservation.save(update_fields=["status", "updated_at"])

    messages.success(request, "Contrat créé à partir de la réservation.")
    return redirect("dashboard:contract_detail", pk=contract.pk)


# ═══════════════════════════ PAYMENTS ═════════════════════════════════

def _payment_filtered_qs(request, params=None, prefix=""):
    """Build filtered Payment queryset from GET params. Returns (qs, filters_dict)."""
    today = date.today()

    src = params or request.GET
    get = src.get
    q = get(f"{prefix}q", "").strip()
    method_f = get(f"{prefix}method", "")
    status_f = get(f"{prefix}status", "")
    period_f = get(f"{prefix}period", "30d")
    sort_by = get(f"{prefix}sort", "date")
    date_from = get(f"{prefix}from", "")
    date_to = get(f"{prefix}to", "")

    agency = _agency(request)
    qs = (
        Payment.objects.for_agency(agency)
        .select_related("contract", "contract__client", "contract__vehicle", "created_by")
    )

    # Period filter
    if period_f == "today":
        qs = qs.filter(created_at__date=today)
    elif period_f == "7d":
        qs = qs.filter(created_at__date__gte=today - timedelta(days=7))
    elif period_f == "custom" and date_from and date_to:
        qs = qs.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
    elif period_f == "all":
        pass  # no date filter
    else:
        # default 30d
        qs = qs.filter(created_at__date__gte=today - timedelta(days=30))

    if q:
        qs = qs.filter(
            Q(contract__client__full_name__icontains=q)
            | Q(contract__vehicle__make__icontains=q)
            | Q(contract__vehicle__model__icontains=q)
            | Q(contract__vehicle__plate_number__icontains=q)
            | Q(reference__icontains=q)
            | Q(contract__pk__icontains=q)
        )
    if method_f:
        qs = qs.filter(method=method_f)
    if status_f:
        qs = qs.filter(status=status_f)

    if sort_by == "amount":
        qs = qs.order_by("-amount")
    elif sort_by == "client":
        qs = qs.order_by("contract__client__full_name")
    else:
        qs = qs.order_by("-created_at")

    filters = {
        "q": q, "method": method_f, "status": status_f,
        "period": period_f, "sort": sort_by,
        "date_from": date_from, "date_to": date_to,
    }
    return qs, filters


@require_perm("billing.view")
def payment_list(request: HttpRequest) -> HttpResponse:
    """Premium payment hub with KPIs, filters, pagination."""
    today = date.today()

    qs, filters = _payment_filtered_qs(request)
    payments = list(qs)

    # ── KPIs (on filtered set) ───────────────────────────────────
    succeeded_qs = [p for p in payments if p.status == "succeeded"]
    total_collected = sum(p.amount for p in succeeded_qs)

    today_collected = sum(
        p.amount for p in succeeded_qs
        if p.created_at.date() == today
    )

    payment_count = len(payments)

    # Method breakdown for dominant method
    method_counts = {}
    for p in succeeded_qs:
        method_counts[p.method] = method_counts.get(p.method, 0) + 1
    dominant_method = max(method_counts, key=method_counts.get) if method_counts else None
    METHOD_LABELS = {"cash": "Espèces", "card_terminal": "Terminal CB", "bank_transfer": "Virement"}
    dominant_label = METHOD_LABELS.get(dominant_method, "-") if dominant_method else "-"

    kpi = {
        "total_collected": total_collected,
        "today_collected": today_collected,
        "count": payment_count,
        "dominant_method": dominant_label,
    }

    # ── Pagination ───────────────────────────────────────────────
    page_num = int(request.GET.get("page", 1))
    per_page = 25
    total_pages = max((len(payments) + per_page - 1) // per_page, 1)
    page_num = max(1, min(page_num, total_pages))
    start = (page_num - 1) * per_page
    page_payments = payments[start:start + per_page]

    return render(request, "dashboard/payments/list.html", {
        "page_id": "payments", "breadcrumb": "Paiements",
        "payments": page_payments, "kpi": kpi,
        "filters": filters,
        "page_num": page_num, "total_pages": total_pages,
        "has_prev": page_num > 1, "has_next": page_num < total_pages,
        "total_count": len(payments),
    })


@require_perm("billing.view")
def payment_export(request: HttpRequest) -> HttpResponse:
    """Export filtered payments as CSV."""
    import csv
    from django.http import StreamingHttpResponse

    qs, _ = _payment_filtered_qs(request)

    class Echo:
        def write(self, value):
            return value

    def rows():
        writer = csv.writer(Echo())
        yield writer.writerow([
            "Date", "Montant", "Devise", "Méthode", "Statut",
            "Référence", "Client", "Véhicule", "Contrat #", "Créé par",
        ])
        for p in qs.iterator():
            yield writer.writerow([
                p.created_at.strftime("%Y-%m-%d %H:%M"),
                str(p.amount),
                p.currency,
                p.get_method_display(),
                p.get_status_display(),
                p.reference or "",
                p.contract.client.full_name if p.contract and p.contract.client else "",
                (f"{p.contract.vehicle.make} {p.contract.vehicle.model} ({p.contract.vehicle.plate_number})"
                 if p.contract and p.contract.vehicle else ""),
                str(p.contract_id) if p.contract_id else "",
                p.created_by.get_full_name() if p.created_by else "",
            ])

    filename = f"paiements_{date.today().isoformat()}.csv"
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # BOM for Excel UTF-8
    response.streaming_content = _prepend_bom(response.streaming_content)
    return response


def _prepend_bom(content):
    """Prepend UTF-8 BOM for Excel compatibility."""
    yield b"\xef\xbb\xbf"
    yield from content


@require_perm("billing.create")
def payment_create(request: HttpRequest, contract_pk: int) -> HttpResponse:
    contract = get_object_or_404(Contract.objects.for_agency(_agency(request)), pk=contract_pk)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            p = form.save(commit=False)
            p.agency = _agency(request)
            p.contract = contract
            p.created_by = request.user
            p.save()
            contract.recalc_payments()
            contract.save(update_fields=["amount_paid", "amount_due", "payment_status"])
            messages.success(request, "Paiement enregistré.")
            # If called from hub, redirect back to hub
            next_url = request.POST.get("next", "")
            if next_url:
                return redirect(next_url)
            return redirect("dashboard:contract_detail", pk=contract_pk)
    return redirect("dashboard:contract_detail", pk=contract_pk)


# ═══════════════════════════ MAINTENANCE ══════════════════════════════

@require_perm("maintenance.view")
def maintenance_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    vehicles = list(Vehicle.objects.for_agency(agency).select_related("agency"))
    can_edit = has_perm(request.user, "maintenance.toggle")

    # Filters
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    sort_by = request.GET.get("sort", "urgency")

    if q:
        vehicles = [v for v in vehicles
                    if q.lower() in f"{v.make} {v.model} {v.plate_number}".lower()]
    if status_filter:
        vehicles = [v for v in vehicles if v.maintenance_status == status_filter]

    # Sort
    if sort_by == "km":
        vehicles.sort(key=lambda v: v.current_km, reverse=True)
    elif sort_by == "date":
        vehicles.sort(key=lambda v: (v.last_maintenance_date or date.min), reverse=True)
    else:  # urgency — blocked first, then urgent, then soon, then ok
        order = {"blocked": 0, "urgent": 1, "soon": 2, "ok": 3}
        vehicles.sort(key=lambda v: (order.get(v.maintenance_status, 9), -v.current_km))

    # KPI counts (reuse already-loaded vehicles to avoid extra query)
    kpi = {"ok": 0, "soon": 0, "urgent": 0, "blocked": 0}
    for v in Vehicle.objects.for_agency(agency).select_related("agency"):
        s = v.maintenance_status
        if s in kpi:
            kpi[s] += 1

    # Forms for modals
    record_form = MaintenanceRecordForm()
    km_form = UpdateKmForm()

    return render(request, "dashboard/maintenance/list.html", {
        "page_id": "maintenance", "breadcrumb": "Maintenance",
        "vehicles": vehicles, "kpi": kpi, "can_edit": can_edit,
        "q": q, "status_filter": status_filter, "sort_by": sort_by,
        "record_form": record_form, "km_form": km_form,
    })


@require_perm("maintenance.toggle")
def maintenance_record(request: HttpRequest, pk: int) -> HttpResponse:
    """Record a maintenance intervention for a vehicle."""
    vehicle = get_object_or_404(Vehicle.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST":
        form = MaintenanceRecordForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                record = form.save(commit=False)
                record.vehicle = vehicle
                record.save()
                # Update vehicle
                vehicle.last_maintenance_km = record.km_at_service
                vehicle.last_maintenance_date = record.date
                vehicle.current_km = max(vehicle.current_km, record.km_at_service)
                vehicle.save(update_fields=[
                    "last_maintenance_km", "last_maintenance_date", "current_km",
                ])
            messages.success(request, f"Entretien enregistré pour {vehicle}.")
        else:
            messages.error(request, "Erreur dans le formulaire d'entretien.")
    return redirect("dashboard:maintenance_list")


@require_perm("maintenance.toggle")
def maintenance_update_km(request: HttpRequest, pk: int) -> HttpResponse:
    """Update current km for a vehicle."""
    vehicle = get_object_or_404(Vehicle.objects.for_agency(_agency(request)), pk=pk)
    if request.method == "POST":
        form = UpdateKmForm(request.POST)
        if form.is_valid():
            vehicle.current_km = form.cleaned_data["current_km"]
            vehicle.save(update_fields=["current_km"])
            messages.success(request, f"Kilométrage mis à jour pour {vehicle}.")
    return redirect("dashboard:maintenance_list")


@require_perm("maintenance.view")
def maintenance_history(request: HttpRequest, pk: int) -> HttpResponse:
    """Show maintenance history for a vehicle."""
    vehicle = get_object_or_404(Vehicle.objects.for_agency(_agency(request)), pk=pk)
    records = vehicle.maintenance_records.all()
    return render(request, "dashboard/maintenance/history.html", {
        "page_id": "maintenance", "breadcrumb": "Historique",
        "vehicle": vehicle, "records": records,
        "can_edit": has_perm(request.user, "maintenance.toggle"),
    })


# ═══════════════════════════ BUSINESS SETTINGS ════════════════════════

@require_perm("settings.view")
def business_settings(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    # Auto-create if missing
    settings_obj, _ = BusinessSettings.objects.get_or_create(agency=agency)
    is_readonly = not has_perm(request.user, "settings.edit")

    if request.method == "POST" and not is_readonly:
        form = BusinessSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "Paramètres enregistrés.")
            return redirect("dashboard:business_settings")
    else:
        form = BusinessSettingsForm(instance=settings_obj, readonly=is_readonly)

    return render(request, "dashboard/business_settings.html", {
        "page_id": "business_settings", "breadcrumb": "Paramètres métier",
        "form": form, "is_readonly": is_readonly, "settings": settings_obj,
    })


# ═══════════════════════════ TEAM ═════════════════════════════════════

def _team_qs(request):
    """Agency-scoped queryset excluding superusers."""
    return User.objects.filter(agency=_agency(request), is_superuser=False)


def _team_ctx(request, qs=None, **extra):
    """Common context for the team split-layout page."""
    if qs is None:
        qs = _team_qs(request).select_related("agency")
    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "")
    status_filter = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(full_name__icontains=q))
    if role_filter:
        qs = qs.filter(role=role_filter)
    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)
    qs = qs.order_by("-date_joined")
    
    ctx = {
        "page_id": "team", "breadcrumb": "Équipe",
        "members": qs, "can_edit": _is_admin(request),
        "q": q, "role_filter": role_filter,
        "status_filter": status_filter,
        "role_choices": User.ROLE_CHOICES,
    }
    ctx.update(extra)
    return ctx


@require_perm("team.view")
def team_list(request: HttpRequest) -> HttpResponse:
    can_create = _has_perm(request, "team.create")
    ctx = _team_ctx(request, panel_mode="create" if can_create else "")
    if can_create:
        ctx["form"] = TeamMemberCreateForm(
            current_role=request.user.role,
        )
        ctx["panel_title"] = "Ajouter un membre"
    return render(request, "dashboard/team/list.html", ctx)


@require_perm("team.create")
def team_create(request: HttpRequest) -> HttpResponse:
    import secrets
    agency = _agency(request)
    cur_role = request.user.role
    if request.method == "POST":
        form = TeamMemberCreateForm(request.POST, current_role=cur_role, agency=agency)
        if form.is_valid():
            chosen_role = form.cleaned_data["role"]
            if cur_role != "agency_owner" and chosen_role == "agency_owner":
                return HttpResponseForbidden("Seul le propriétaire peut créer un autre propriétaire.")
            password = secrets.token_urlsafe(10)
            user = User(
                email=form.cleaned_data["email"],
                username=form.cleaned_data["email"],
                full_name=form.cleaned_data.get("full_name", ""),
                phone=form.cleaned_data.get("phone", ""),
                role=chosen_role,
                agency=agency,
            )
            user.set_password(password)
            user.save()
            messages.success(
                request,
                f"Membre ajouté ! Mot de passe temporaire : {password} — "
                f"Communiquez-le de manière sécurisée.",
            )
            return redirect("dashboard:team")
    else:
        form = TeamMemberCreateForm(current_role=cur_role, agency=agency)
    ctx = _team_ctx(request, form=form, panel_mode="create", panel_title="Ajouter un membre")
    return render(request, "dashboard/team/list.html", ctx)


@require_perm("team.edit")
def team_edit(request: HttpRequest, pk: int) -> HttpResponse:
    member = get_object_or_404(_team_qs(request), pk=pk)
    cur_role = request.user.role
    if cur_role != "agency_owner" and member.role == "agency_owner":
        return HttpResponseForbidden("Vous ne pouvez pas modifier le propriétaire.")
    if request.method == "POST":
        form = TeamMemberEditForm(request.POST, instance=member, current_role=cur_role)
        if form.is_valid():
            chosen_role = form.cleaned_data.get("role", member.role)
            if cur_role != "agency_owner" and chosen_role == "agency_owner":
                return HttpResponseForbidden("Seul le propriétaire peut promouvoir en propriétaire.")
            form.save()
            messages.success(request, "Membre mis à jour.")
            return redirect("dashboard:team")
    else:
        form = TeamMemberEditForm(instance=member, current_role=cur_role)
    ctx = _team_ctx(
        request, form=form, panel_mode="edit",
        panel_title=f"Modifier — {member.full_name or member.email}",
        editing_member=member,
    )
    return render(request, "dashboard/team/list.html", ctx)


@require_perm("team.deactivate")
def team_toggle_active(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden("POST requis.")
    member = get_object_or_404(_team_qs(request), pk=pk)
    cur_role = request.user.role
    if cur_role != "agency_owner" and member.role == "agency_owner":
        return HttpResponseForbidden("Vous ne pouvez pas modifier le propriétaire.")
    if member.role == "agency_owner" and member.is_active:
        owner_count = _team_qs(request).filter(role="agency_owner", is_active=True).count()
        if owner_count <= 1:
            messages.error(request, "Impossible de désactiver le dernier propriétaire.")
            return redirect("dashboard:team")
    member.is_active = not member.is_active
    User.objects.filter(pk=member.pk).update(is_active=member.is_active)
    label = "activé" if member.is_active else "désactivé"
    messages.success(request, f"Membre {label}.")
    return redirect("dashboard:team")


@require_perm("team.delete")
def team_delete(request: HttpRequest, pk: int) -> HttpResponse:
    member = get_object_or_404(_team_qs(request), pk=pk)
    cur_role = request.user.role
    if cur_role != "agency_owner" and member.role == "agency_owner":
        return HttpResponseForbidden("Vous ne pouvez pas supprimer le propriétaire.")
    if member.role == "agency_owner":
        owner_count = _team_qs(request).filter(role="agency_owner", is_active=True).count()
        if owner_count <= 1:
            messages.error(request, "Impossible de supprimer le dernier propriétaire.")
            return redirect("dashboard:team")
    if request.method == "POST":
        member.delete()
        messages.success(request, "Membre supprimé.")
        return redirect("dashboard:team")
    return render(request, "dashboard/team/confirm_delete.html", {
        "page_id": "team", "breadcrumb": "Équipe",
        "member": member, "title": f"Supprimer — {member.full_name or member.email}",
    })


# ═══════════════════════════ ACCOUNT ══════════════════════════════════

@require_perm("dashboard.view")
def account(request: HttpRequest) -> HttpResponse:
    user = request.user
    agency = get_object_or_404(Agency, pk=_agency(request).pk)
    role = user.role
    is_readonly = role == "read_only"
    saved = False

    if request.method == "POST" and not is_readonly:
        user_form = AccountProfileForm(request.POST, instance=user)
        agency_form = AgencyProfileForm(request.POST, request.FILES, instance=agency, role=role)
        if user_form.is_valid() and agency_form.is_valid():
            with transaction.atomic():
                user_form.save()
                agency_form.save()
            messages.success(request, "Profil mis à jour avec succès.")
            return redirect("dashboard:account")
    else:
        user_form = AccountProfileForm(instance=user)
        agency_form = AgencyProfileForm(instance=agency, role=role)
        if is_readonly:
            for field in user_form.fields.values():
                field.disabled = True
        saved = request.GET.get("saved") == "1"

    return render(request, "dashboard/account.html", {
        "page_id": "account", "breadcrumb": "Mon compte",
        "user_form": user_form, "agency_form": agency_form,
        "agency": agency, "is_readonly": is_readonly, "saved": saved,
    })


# ═══════════════════════════ SITE PUBLIC ══════════════════════════════

def _ensure_site_data(agency):
    """Get or create AgencySiteSettings + default sections for agency."""
    ss, created = AgencySiteSettings.objects.get_or_create(agency=agency)
    if created:
        ss.ensure_defaults()
        ss.save()
    # Ensure all default sections exist
    for sec in DEFAULT_HOME_SECTIONS:
        AgencySiteSection.objects.get_or_create(
            agency=agency, page="home", key=sec["key"],
            defaults={"label": sec["label"], "description": sec["description"], "order": sec["order"]},
        )
    sections = AgencySiteSection.objects.filter(agency=agency, page="home").order_by("order")
    return ss, sections


@require_perm("public_site.view")
def site_public_settings(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    can_edit = _has_perm(request, "public_site.edit")
    is_owner = request.user.role == "agency_owner"
    is_admin = request.user.role in ("agency_owner", "agency_manager")
    ss, sections = _ensure_site_data(agency)
    q = request.GET.get("q", "").strip()
    flt = request.GET.get("filter", "")
    cms_edit_id = request.GET.get("cms_edit")
    cms_creating = request.GET.get("cms_create") == "1"
    active_panel = request.GET.get("panel") or ("pages" if cms_edit_id or cms_creating else "branding")
    cms_editing = None

    if request.method == "POST" and can_edit:
        action = request.POST.get("action", "save")
        form = AgencySiteSettingsForm(request.POST, request.FILES, instance=ss)

        if form.is_valid():
            with transaction.atomic():
                site = form.save(commit=False)

                # Sync theme to agency for backward compat
                agency.theme = site.theme_key
                agency.primary_color = site.primary_color
                agency.secondary_color = site.secondary_color
                agency.public_enabled = site.is_public_enabled
                agency.maintenance_mode = site.is_maintenance_enabled
                agency.public_headline = site.hero_title
                agency.public_tagline = site.hero_subtitle
                agency.public_phone = site.contact_phone
                agency.public_whatsapp = site.whatsapp
                agency.public_city = site.city

                # Section toggles
                for sec in sections:
                    sec.enabled = request.POST.get(f"section_{sec.key}") == "on"
                    sec.save(update_fields=["enabled"])

                if action == "publish" and is_owner:
                    site.status = "published"
                    messages.success(request, "Site publié avec succès !")
                else:
                    site.status = "draft"
                    messages.success(request, "Modifications enregistrées (brouillon).")

                site.save()
                agency.save(update_fields=[
                    "theme", "primary_color", "secondary_color",
                    "public_enabled", "maintenance_mode",
                    "public_headline", "public_tagline",
                    "public_phone", "public_whatsapp", "public_city",
                ])

            return redirect("dashboard:site_public_settings")
    else:
        form = AgencySiteSettingsForm(instance=ss)

    pages = PublicPage.objects.for_agency(agency)
    if q:
        pages = pages.filter(title__icontains=q)
    if flt == "published":
        pages = pages.filter(is_published=True)
    elif flt == "draft":
        pages = pages.filter(is_published=False)
    elif flt == "nav":
        pages = pages.filter(show_in_nav=True)

    if cms_edit_id and is_admin:
        cms_editing = get_object_or_404(PublicPage, pk=cms_edit_id, agency=agency)

    return render(request, "dashboard/site_public_settings.html", {
        "page_id": "site_public", "breadcrumb": "Site public",
        "agency": agency, "ss": ss, "form": form,
        "sections": sections, "themes": THEMES,
        "can_edit": can_edit, "is_owner": is_owner,
        "pages": pages, "cms_editing": cms_editing,
        "cms_creating": cms_creating, "q": q,
        "filter": flt, "is_admin": is_admin,
        "active_panel": active_panel,
    })


# ═══════════════════════════ RESERVATIONS ════════════════════════════

@require_perm("reservations.view")
def reservation_list(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    qs = ReservationRequest.objects.for_agency(agency).select_related("vehicle")

    # KPIs
    today = date.today()
    kpi_pending = qs.filter(status="pending").count()
    kpi_confirmed = qs.filter(status="confirmed").count()
    kpi_contracted = qs.filter(status="contracted").count()
    kpi_rejected = qs.filter(status="rejected").count()
    kpi_today = qs.filter(created_at__date=today).count()

    # Filters
    status_filter = request.GET.get("status", "")
    vehicle_filter = request.GET.get("vehicle", "")
    search = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "newest")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if vehicle_filter:
        qs = qs.filter(vehicle_id=vehicle_filter)
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    if sort == "oldest":
        qs = qs.order_by("created_at")
    elif sort == "start_date":
        qs = qs.order_by("start_date")
    else:
        qs = qs.order_by("-created_at")

    vehicles = Vehicle.objects.for_agency(agency).order_by("make", "model")

    return render(request, "dashboard/reservations/list.html", {
        "page_id": "reservations", "breadcrumb": "Réservations",
        "reservations": qs[:200],
        "kpi_pending": kpi_pending, "kpi_confirmed": kpi_confirmed,
        "kpi_contracted": kpi_contracted,
        "kpi_rejected": kpi_rejected, "kpi_today": kpi_today,
        "vehicles": vehicles,
        "status_filter": status_filter, "vehicle_filter": vehicle_filter,
        "search": search, "sort": sort,
    })


@require_perm("reservations.view")
def reservation_detail(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency).select_related("vehicle"), pk=pk,
    )
    can_manage = _has_perm(request, "reservations.manage")

    from clients.models import NegotiationMessage
    nego_messages = NegotiationMessage.objects.filter(reservation=reservation)
    # Mark client messages as read
    nego_messages.filter(sender="client", is_read=False).update(is_read=True)
    return render(request, "dashboard/reservations/detail.html", {
        "page_id": "reservations", "breadcrumb": "Réservation",
        "r": reservation, "can_manage": can_manage,
        "nego_messages": nego_messages,
    })


@require_perm("reservations.manage")
def reservation_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency), pk=pk,
    )
    if reservation.status != "pending":
        messages.error(request, "Cette demande n'est plus en attente.")
        return redirect("dashboard:reservation_detail", pk=pk)

    # Block if vehicle already has an active contract
    existing_contract = Contract.vehicle_has_active_contract(reservation.vehicle)
    if existing_contract:
        messages.error(
            request,
            f"Le véhicule {reservation.vehicle} est déjà sous contrat "
            f"(#{existing_contract.pk} — {existing_contract.get_status_display()}). "
            f"Impossible de confirmer cette réservation.",
        )
        return redirect("dashboard:reservation_detail", pk=pk)

    # Re-check conflict at confirm time
    with transaction.atomic():
        if has_date_conflict(reservation.vehicle, reservation.start_date, reservation.end_date, exclude_pk=pk):
            messages.error(
                request,
                "Conflit de dates : une autre réservation confirmée existe déjà pour ce véhicule sur cette période.",
            )
            return redirect("dashboard:reservation_detail", pk=pk)

        decision_msg = request.POST.get("decision_message", "").strip()[:180]
        reservation.status = "confirmed"
        reservation.decision_message = decision_msg or "Réservation acceptée, nous vous contactons."
        reservation.save(update_fields=["status", "decision_message", "updated_at"])

    # Notify portal client if linked
    if reservation.client_account_id:
        ClientNotification.objects.create(
            client=reservation.client_account,
            title="Réservation confirmée",
            message=f"Votre réservation pour {reservation.vehicle} du {reservation.start_date} au {reservation.end_date} a été confirmée. {reservation.decision_message}",
            notif_type="success",
        )

    # Email client if email provided
    _email_client_decision(reservation)
    messages.success(request, f"Réservation #{pk} confirmée.")
    return redirect("dashboard:reservation_detail", pk=pk)


@require_perm("reservations.manage")
def reservation_reject(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    reservation = get_object_or_404(
        ReservationRequest.objects.for_agency(agency), pk=pk,
    )
    if reservation.status != "pending":
        messages.error(request, "Cette demande n'est plus en attente.")
        return redirect("dashboard:reservation_detail", pk=pk)

    decision_msg = request.POST.get("decision_message", "").strip()[:180]
    reservation.status = "rejected"
    reservation.decision_message = decision_msg or "Ce véhicule n'est plus disponible, choisissez-en un autre."
    reservation.save(update_fields=["status", "decision_message", "updated_at"])

    # Notify portal client if linked
    if reservation.client_account_id:
        ClientNotification.objects.create(
            client=reservation.client_account,
            title="Réservation refusée",
            message=f"Votre réservation pour {reservation.vehicle} du {reservation.start_date} au {reservation.end_date} a été refusée. {reservation.decision_message}",
            notif_type="warn",
        )

    _email_client_decision(reservation)
    messages.success(request, f"Réservation #{pk} refusée.")
    return redirect("dashboard:reservation_detail", pk=pk)


def _email_client_decision(reservation):
    """Send email to client about reservation decision (if email provided)."""
    if not reservation.email:
        return
    try:
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        status_label = "confirmée" if reservation.status == "confirmed" else "refusée"
        tracking_url = (
            f"/a/{reservation.agency.slug}/reservation/{reservation.public_token}/"
            f"?s={reservation.public_secret}"
        )
        send_mail(
            subject=f"Votre réservation a été {status_label} — {reservation.agency.name}",
            message=(
                f"Bonjour {reservation.full_name},\n\n"
                f"Votre demande de réservation pour {reservation.vehicle} "
                f"du {reservation.start_date} au {reservation.end_date} "
                f"a été {status_label}.\n\n"
                f"Message de l'agence : {reservation.decision_message}\n\n"
                f"Suivez votre réservation ici : {tracking_url}\n\n"
                f"— {reservation.agency.name}"
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.email],
            fail_silently=True,
        )
    except Exception:
        pass


# ═══════════════════════════ NEGOTIATION ══════════════════════════════

@require_perm("reservations.manage")
def nego_accept_offer(request: HttpRequest, pk: int) -> HttpResponse:
    """Agency accepts the client's price offer."""
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    r = get_object_or_404(ReservationRequest.objects.for_agency(agency), pk=pk)
    if r.negotiation_status != "pending_offer":
        messages.error(request, "Cette offre n'est plus en attente.")
        return redirect("dashboard:reservation_detail", pk=pk)

    # Block if vehicle already has an active contract
    existing_contract = Contract.vehicle_has_active_contract(r.vehicle)
    if existing_contract:
        messages.error(
            request,
            f"Le véhicule {r.vehicle} est déjà sous contrat "
            f"(#{existing_contract.pk} — {existing_contract.get_status_display()}). "
            f"Impossible d'accepter cette offre.",
        )
        return redirect("dashboard:reservation_detail", pk=pk)

    with transaction.atomic():
        if has_date_conflict(r.vehicle, r.start_date, r.end_date, exclude_pk=pk):
            messages.error(request, "Conflit de dates détecté.")
            return redirect("dashboard:reservation_detail", pk=pk)
        r.daily_price_accepted = r.daily_price_offer
        r.negotiation_status = "accepted"
        r.status = "confirmed"
        r.decision_message = "Offre acceptée, réservation confirmée."
        r.save(update_fields=[
            "daily_price_accepted", "negotiation_status",
            "status", "decision_message", "updated_at",
        ])

    if r.client_account_id:
        ClientNotification.objects.create(
            client=r.client_account,
            title="Offre acceptée",
            message=f"Votre offre de {r.daily_price_offer}/jour pour {r.vehicle} a été acceptée. Réservation confirmée !",
            notif_type="success",
        )
    _email_client_decision(r)
    messages.success(request, f"Offre acceptée — réservation #{pk} confirmée.")
    return redirect("dashboard:reservation_detail", pk=pk)


@require_perm("reservations.manage")
def nego_counter_offer(request: HttpRequest, pk: int) -> HttpResponse:
    """Agency sends a counter-offer to the client."""
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    r = get_object_or_404(ReservationRequest.objects.for_agency(agency), pk=pk)
    if r.negotiation_status != "pending_offer":
        messages.error(request, "Cette offre n'est plus en attente.")
        return redirect("dashboard:reservation_detail", pk=pk)

    try:
        from decimal import Decimal
        counter_price = Decimal(request.POST.get("counter_price", "0"))
    except Exception:
        messages.error(request, "Prix invalide.")
        return redirect("dashboard:reservation_detail", pk=pk)

    if counter_price <= 0:
        messages.error(request, "Le prix doit être supérieur à 0.")
        return redirect("dashboard:reservation_detail", pk=pk)

    agency_msg = request.POST.get("agency_message", "").strip()[:500]
    r.daily_price_counter = counter_price
    r.negotiation_status = "countered"
    r.agency_message = agency_msg
    r.save(update_fields=[
        "daily_price_counter", "negotiation_status", "agency_message", "updated_at",
    ])

    if r.client_account_id:
        ClientNotification.objects.create(
            client=r.client_account,
            title="Contre-offre reçue",
            message=f"L'agence propose {counter_price}/jour pour {r.vehicle}. {agency_msg}".strip(),
            notif_type="info",
        )
    messages.success(request, f"Contre-offre de {counter_price}/jour envoyée.")
    return redirect("dashboard:reservation_detail", pk=pk)


@require_perm("reservations.manage")
def nego_refuse(request: HttpRequest, pk: int) -> HttpResponse:
    """Agency refuses the client's price offer and rejects the reservation."""
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    r = get_object_or_404(ReservationRequest.objects.for_agency(agency), pk=pk)
    if r.negotiation_status not in ("pending_offer", "countered"):
        messages.error(request, "Aucune négociation en cours.")
        return redirect("dashboard:reservation_detail", pk=pk)

    r.negotiation_status = "refused"
    r.status = "rejected"
    r.decision_message = "Offre refusée. Choisissez un autre véhicule ou acceptez le prix affiché."
    r.save(update_fields=[
        "negotiation_status", "status", "decision_message", "updated_at",
    ])

    if r.client_account_id:
        ClientNotification.objects.create(
            client=r.client_account,
            title="Offre refusée",
            message=f"Votre offre pour {r.vehicle} a été refusée. {r.decision_message}",
            notif_type="warn",
        )
    _email_client_decision(r)
    messages.success(request, f"Offre refusée — réservation #{pk} rejetée.")
    return redirect("dashboard:reservation_detail", pk=pk)


@require_perm("reservations.manage")
def nego_send_message(request: HttpRequest, pk: int) -> HttpResponse:
    """Agency sends a negotiation chat message to the client."""
    if request.method != "POST":
        return HttpResponseForbidden()
    agency = _agency(request)
    r = get_object_or_404(ReservationRequest.objects.for_agency(agency), pk=pk)

    body = request.POST.get("body", "").strip()[:1000]
    if not body:
        messages.error(request, "Le message ne peut pas être vide.")
        return redirect("dashboard:reservation_detail", pk=pk)

    from clients.models import NegotiationMessage, ClientNotification
    NegotiationMessage.objects.create(
        reservation=r, sender="agency", body=body,
    )

    if r.client_account:
        ClientNotification.objects.create(
            client=r.client_account,
            title="Nouveau message de l'agence",
            message=f"L'agence a envoyé un message concernant votre réservation pour {r.vehicle}.",
            notif_type="info",
        )

    messages.success(request, "Message envoyé.")
    return redirect("dashboard:reservation_detail", pk=pk)


# ═══════════════════════════ SUBSCRIPTION (AGENCY) ═══════════════════

@require_perm("dashboard.view")
def subscription(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)
    access = get_agency_access(agency)

    sync_access(access)

    if request.method == "POST" and request.POST.get("plan_code"):
        plan_code = request.POST.get("plan_code", "").strip()
        if plan_code in PLAN_CONFIGS:
            apply_plan_to_access(access, plan_code)
            users_count = agency.users.count()
            vehicles_count = agency.vehicles.count()
            messages.success(request, f"Plan {access.plan_name} activé.")
            if access.max_users and users_count > access.max_users:
                messages.warning(request, f"Utilisateurs actuels: {users_count} (limite {access.max_users}).")
            if access.max_vehicles and vehicles_count > access.max_vehicles:
                messages.warning(request, f"Véhicules actuels: {vehicles_count} (limite {access.max_vehicles}).")
        else:
            messages.error(request, "Plan invalide.")
        return redirect("dashboard:subscription")

    # Handle proof upload
    if request.method == "POST" and request.FILES.get("proof_image"):
        img = request.FILES["proof_image"]
        # Validate
        allowed_types = ("image/jpeg", "image/png", "image/webp")
        max_size = 5 * 1024 * 1024  # 5MB
        errors = []
        if img.content_type not in allowed_types:
            errors.append("Format non supporté. Utilisez JPG, PNG ou WebP.")
        if img.size > max_size:
            errors.append("Fichier trop volumineux (max 5 Mo).")
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            PaymentProof.objects.create(
                access=access,
                image=img,
                uploaded_by=request.user,
            )
            messages.success(request, "Preuve de paiement envoyée ! Validation sous 24h max.")
        return redirect("dashboard:subscription")

    proofs = PaymentProof.objects.filter(access=access).order_by("-uploaded_at")[:10]
    latest_proof = proofs.first() if proofs else None

    # PayPal config for template
    from core.services_platform import get_paypal_config
    cfg = get_paypal_config()
    paypal_enabled = cfg.get("enable_paypal_auto", False) and bool(cfg.get("plan_id"))

    # PayPalSubscription detail (next billing, payer email)
    pp_sub = None
    try:
        from core.models_paypal_subscription import PayPalSubscription
        pp_sub = PayPalSubscription.objects.get(access=access)
    except Exception:
        pass

    plan_cards = [PLAN_CONFIGS["starter"], PLAN_CONFIGS["business"], PLAN_CONFIGS["enterprise"]]
    return render(request, "dashboard/subscription.html", {
        "page_id": "subscription", "breadcrumb": "Abonnement",
        "access": access, "proofs": proofs, "latest_proof": latest_proof,
        "billing_mode": access.billing_mode,
        "paypal_status": access.paypal_status,
        "paypal_subscription_id": access.paypal_subscription_id,
        "paypal_last_event_at": access.paypal_last_event_at,
        "access_source_label": access.access_source_label,
        "paypal_enabled": paypal_enabled,
        "pp_sub": pp_sub,
        "plan_cards": plan_cards,
    })


# ═══════════════════════════ PAYPAL SUBSCRIPTION FLOW ═════════════════

@require_perm("dashboard.view")
def start_paypal_subscription(request: HttpRequest) -> HttpResponse:
    """Create a PayPal subscription via API and redirect to PayPal approval."""
    if request.method != "POST":
        return redirect("dashboard:subscription")

    agency = _agency(request)
    access = get_agency_access(agency)

    from core.services_paypal_api import create_subscription
    from core.services_platform import get_paypal_config

    cfg = get_paypal_config()
    if not cfg.get("enable_paypal_auto"):
        messages.warning(request, "Le paiement PayPal n'est pas activé par l'administrateur.")
        return redirect("dashboard:subscription")

    if not cfg.get("plan_id"):
        messages.error(request, "Configuration PayPal incomplète. Contactez l'administrateur.")
        return redirect("dashboard:subscription")

    return_url = request.build_absolute_uri("/dashboard/subscription/paypal/return/")
    cancel_url = request.build_absolute_uri("/dashboard/subscription/paypal/cancel/")

    result = create_subscription(
        return_url=return_url,
        cancel_url=cancel_url,
        custom_id=str(agency.pk),
        cfg=cfg,
    )

    if not result["ok"]:
        messages.error(request, f"Erreur PayPal: {result['message']}")
        return redirect("dashboard:subscription")

    # Create PayPalSubscription record in APPROVAL_PENDING state
    from core.models_paypal_subscription import PayPalSubscription
    PayPalSubscription.objects.update_or_create(
        access=access,
        defaults={
            "paypal_subscription_id": result["subscription_id"],
            "status": "APPROVAL_PENDING",
            "plan_id": cfg.get("plan_id", ""),
            "product_id": cfg.get("product_id", ""),
        },
    )

    # Redirect to PayPal approval page
    return redirect(result["approve_url"])


@require_perm("dashboard.view")
def paypal_return_success(request: HttpRequest) -> HttpResponse:
    """User returns from PayPal after approving the subscription."""
    agency = _agency(request)
    access = get_agency_access(agency)

    subscription_id = request.GET.get("subscription_id", "")
    if not subscription_id:
        messages.info(request, "Retour depuis PayPal (aucun ID de souscription).")
        return redirect("dashboard:subscription")

    if access.billing_mode == "paypal" and access.paypal_subscription_id == subscription_id:
        messages.info(request, "Abonnement PayPal déjà actif.")
        return redirect("dashboard:subscription")

    # Fetch subscription details from PayPal to confirm status
    from core.services_paypal_api import get_subscription_details
    details = get_subscription_details(subscription_id)

    if details["ok"]:
        pp_data = details["data"]
        pp_status = pp_data.get("status", "")

        if pp_status in ("ACTIVE", "APPROVED"):
            switch_to_paypal(access, subscription_id, by_user=request.user)

            # Update PayPalSubscription detail
            from core.models_paypal_subscription import PayPalSubscription
            try:
                pp_sub = PayPalSubscription.objects.get(access=access)
                pp_sub.paypal_subscription_id = subscription_id
                pp_sub.status = "ACTIVE" if pp_status == "ACTIVE" else "APPROVED"
                pp_sub.payer_email = (
                    pp_data.get("subscriber", {}).get("email_address", "")
                )
                billing_info = pp_data.get("billing_info", {})
                next_billing = billing_info.get("next_billing_time", "")
                if next_billing:
                    from django.utils.dateparse import parse_datetime
                    dt = parse_datetime(next_billing)
                    if dt:
                        pp_sub.next_billing_time = dt
                pp_sub.save()
            except PayPalSubscription.DoesNotExist:
                PayPalSubscription.objects.create(
                    access=access,
                    paypal_subscription_id=subscription_id,
                    status="ACTIVE" if pp_status == "ACTIVE" else "APPROVED",
                    plan_id=pp_data.get("plan_id", ""),
                    payer_email=pp_data.get("subscriber", {}).get("email_address", ""),
                )

            # Create admin alert for mode upgrade
            from core.models_admin_alert import AdminAlert
            AdminAlert.objects.create(
                alert_type="mode_upgrade",
                agency=agency,
                message=f"L'agence {agency.name} est passée en paiement PayPal automatique.",
            )

            messages.success(
                request,
                "Abonnement PayPal activé ! Renouvellement automatique chaque mois."
            )
        else:
            messages.warning(
                request,
                f"Statut PayPal: {pp_status}. L'abonnement n'est pas encore actif."
            )
    else:
        # Could not verify with PayPal, but subscription_id was returned
        switch_to_paypal(access, subscription_id, by_user=request.user)
        messages.success(
            request,
            "Abonnement PayPal enregistré. Confirmation en attente du webhook."
        )

    return redirect("dashboard:subscription")


@require_perm("dashboard.view")
def paypal_cancel_return(request: HttpRequest) -> HttpResponse:
    """User cancelled the PayPal checkout flow."""
    messages.info(request, "Paiement PayPal annulé. Aucune modification apportée.")
    return redirect("dashboard:subscription")


# ═══════════════════════════ SUPERADMIN — AGENCIES ACCESS ════════════

def _require_superadmin(view_func):
    """Decorator: only superusers can access."""
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return HttpResponseForbidden("Accès réservé au super-administrateur.")
        return view_func(request, *args, **kwargs)
    return wrapper


@_require_superadmin
def admin_agencies_access(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    qs = AgencyAccess.objects.select_related("agency").all()

    # KPIs
    kpi_trial = qs.filter(status="trial").count()
    kpi_active = qs.filter(status="active").count()
    kpi_suspended = qs.filter(status="suspended").count()
    from datetime import timedelta as td
    soon = now + td(hours=48)
    kpi_pending_proofs = PaymentProof.objects.filter(status="pending").count()
    kpi_expiring = qs.filter(
        status__in=("trial", "active"),
        access_ends_at__lte=soon,
        access_ends_at__gt=now,
    ).count()

    # Filters
    status_filter = request.GET.get("status", "")
    search = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "urgent")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(agency__name__icontains=search)
            | Q(agency__users__email__icontains=search)
        ).distinct()

    pending_only = request.GET.get("pending", "")
    if pending_only:
        qs = qs.filter(proofs__status="pending").distinct()

    if sort == "name":
        qs = qs.order_by("agency__name")
    elif sort == "newest":
        qs = qs.order_by("-created_at")
    else:
        qs = qs.order_by("access_ends_at")

    # Attach owner email + latest proof for each
    agencies_data = []
    for acc in qs[:200]:
        owner = acc.agency.users.filter(role="agency_owner").first()
        latest_proof = PaymentProof.objects.filter(access=acc).order_by("-uploaded_at").first()
        agencies_data.append({
            "access": acc,
            "owner_email": owner.email if owner else "—",
            "latest_proof": latest_proof,
        })

    return render(request, "dashboard/admin/agencies_access.html", {
        "page_id": "admin_access", "breadcrumb": "Gestion accès agences",
        "agencies_data": agencies_data,
        "kpi_trial": kpi_trial, "kpi_active": kpi_active,
        "kpi_suspended": kpi_suspended, "kpi_expiring": kpi_expiring,
        "kpi_pending_proofs": kpi_pending_proofs,
        "status_filter": status_filter, "search": search, "sort": sort,
        "pending_only": pending_only,
    })


@_require_superadmin
def admin_agency_access_detail(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_object_or_404(AgencyAccess.objects.select_related("agency"), pk=pk)
    proofs = PaymentProof.objects.filter(access=access).order_by("-uploaded_at")
    owner = access.agency.users.filter(role="agency_owner").first()
    return render(request, "dashboard/admin/agency_access_detail.html", {
        "page_id": "admin_access", "breadcrumb": f"Accès — {access.agency.name}",
        "access": access, "proofs": proofs, "owner": owner,
    })


@_require_superadmin
def admin_access_renew(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    renew_access(access, by_user=request.user)
    messages.success(
        request,
        f"{access.agency.name} renouvelé jusqu'au {access.access_ends_at.strftime('%d/%m/%Y %H:%M')}.",
    )
    return redirect(request.POST.get("next", "dashboard:admin_agencies_access"))


@_require_superadmin
def admin_access_suspend(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    reason = request.POST.get("reason", "").strip()[:500]
    suspend_access(access, reason=reason, by_user=request.user)
    messages.success(request, f"{access.agency.name} suspendu.")
    return redirect(request.POST.get("next", "dashboard:admin_agencies_access"))


@_require_superadmin
def admin_access_bonus(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    days = int(request.POST.get("days", 7))
    grant_bonus_days(access, days=days, by_user=request.user)
    messages.success(request, f"+{days} jours accordés à {access.agency.name}.")
    return redirect(request.POST.get("next", "dashboard:admin_agencies_access"))


@_require_superadmin
def admin_proof_approve(request: HttpRequest, proof_pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    proof = get_object_or_404(PaymentProof.objects.select_related("access", "access__agency"), pk=proof_pk)
    proof.status = "approved"
    proof.reviewed_by = request.user
    proof.reviewed_at = timezone.now()
    proof.review_note = request.POST.get("review_note", "").strip()[:500]
    proof.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    # Auto-renew on approval
    renew_access(proof.access, by_user=request.user)
    messages.success(
        request,
        f"Preuve approuvée + {proof.agency.name} renouvelé jusqu'au "
        f"{proof.access.access_ends_at.strftime('%d/%m/%Y %H:%M')}.",
    )
    next_url = request.POST.get("next", "dashboard:admin_agencies_access")
    return redirect(next_url)


@_require_superadmin
def admin_proof_reject(request: HttpRequest, proof_pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    proof = get_object_or_404(PaymentProof, pk=proof_pk)
    proof.status = "rejected"
    proof.reviewed_by = request.user
    proof.reviewed_at = timezone.now()
    proof.review_note = request.POST.get("review_note", "").strip()[:500] or "Preuve non conforme."
    proof.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    messages.success(request, f"Preuve #{proof.pk} rejetée.")
    next_url = request.POST.get("next", "dashboard:admin_agencies_access")
    return redirect(next_url)


@_require_superadmin
def admin_access_save_notes(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseForbidden()
    access = get_object_or_404(AgencyAccess, pk=pk)
    access.notes_internal = request.POST.get("notes_internal", "").strip()[:2000]
    access.save(update_fields=["notes_internal", "updated_at"])
    messages.success(request, "Notes enregistrées.")
    return redirect("dashboard:admin_agency_access_detail", pk=pk)


# ═══════════════════════════ THEME TOGGLE API ════════════════════════

@require_perm("dashboard.view")
def api_set_theme(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    theme = data.get("theme", "")
    if theme not in ("dark", "gaboom"):
        return JsonResponse({"error": "Invalid theme"}, status=400)
    agency = _agency(request)
    from agencies.models import AgencyThemeSettings
    ts, _ = AgencyThemeSettings.objects.get_or_create(agency=agency)
    ts.theme_choice = theme
    ts.save(update_fields=["theme_choice"])
    return JsonResponse({"ok": True, "theme": theme})
