import json
import logging
import math
import random
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from agencies.models import (
    Agency, GeoZone, GeofenceEvent, GPSAlert, GPSDevice, GPSPositionLog, Vehicle, VehicleZoneState,
)
from agencies.services import get_agency_access
from billing.models import Contract
from core.permissions import require_perm


def _agency(request: HttpRequest) -> Agency:
    return request.user.agency

def _gps_allowed(request: HttpRequest) -> bool:
    access = get_agency_access(_agency(request))
    return access.plan_has_feature("gps_tracking")


def _process_gps_update(device, lat, lng, speed=None, heading=None, recorded_at=None, source="device", last_ip=None):
    now = timezone.now()
    vehicle = device.linked_vehicle
    if not vehicle:
        vehicle = Vehicle.objects.filter(
            agency=device.agency, gps_imei=device.imei, gps_enabled=True,
        ).first()
    if not vehicle or not vehicle.gps_enabled:
        return {"ok": False, "error": "Vehicle not found or GPS disabled"}

    vehicle.last_lat = Decimal(str(lat))
    vehicle.last_lng = Decimal(str(lng))
    vehicle.last_gps_speed = Decimal(str(speed)) if speed is not None else None
    vehicle.last_gps_update = now
    vehicle.save(update_fields=["last_lat", "last_lng", "last_gps_speed", "last_gps_update"])

    GPSPositionLog.objects.create(
        vehicle=vehicle,
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
        speed=Decimal(str(speed)) if speed is not None else None,
        heading=Decimal(str(heading)) if heading is not None else None,
        source=source,
        recorded_at=recorded_at or now,
    )

    geofence_result = _check_geofences(vehicle, lat, lng, recorded_at or now)
    alerts_triggered = geofence_result["alerts_triggered"]
    active_contract = None
    try:
        bs = vehicle.agency.business_settings
        if bs.gps_speed_limit and speed and float(speed) > bs.gps_speed_limit:
            active_contract = Contract.vehicle_has_active_contract(vehicle)
            GPSAlert.objects.create(
                agency=vehicle.agency,
                vehicle=vehicle,
                contract=active_contract,
                alert_type="speed",
                lat=Decimal(str(lat)),
                lng=Decimal(str(lng)),
                message=f"Vitesse {speed} km/h — limite {bs.gps_speed_limit} km/h",
            )
            alerts_triggered += 1
    except Exception:
        pass

    device.last_seen_at = now
    if last_ip:
        device.last_ip = last_ip
    if not device.linked_vehicle:
        device.linked_vehicle = vehicle
    device.save(update_fields=["last_seen_at", "last_ip", "linked_vehicle"])

    return {
        "ok": True,
        "vehicle": vehicle,
        "alerts_triggered": alerts_triggered,
        "geofence": geofence_result,
        "ts_server": now,
    }


def _generate_simulated_points(vehicle, mode="normal", count=10):
    base_lat = float(vehicle.last_lat) if vehicle.last_lat is not None else None
    base_lng = float(vehicle.last_lng) if vehicle.last_lng is not None else None
    if base_lat is None or base_lng is None:
        zone = GeoZone.objects.filter(agency=vehicle.agency, is_active=True).first()
        if zone:
            base_lat = float(zone.center_lat)
            base_lng = float(zone.center_lng)
        else:
            base_lat, base_lng = 0.0, 0.0

    if mode == "zone_test":
        zone = GeoZone.objects.filter(agency=vehicle.agency, is_active=True).first()
        if zone:
            inside_lat = float(zone.center_lat)
            inside_lng = float(zone.center_lng)
            outside_lat = float(zone.center_lat) + float(zone.radius_km) * 0.02 + 0.01
            outside_lng = float(zone.center_lng) + float(zone.radius_km) * 0.02 + 0.01
            return [
                {"lat": outside_lat, "lng": outside_lng, "speed": 10, "heading": 90},
                {"lat": inside_lat, "lng": inside_lng, "speed": 8, "heading": 120},
                {"lat": inside_lat + 0.0002, "lng": inside_lng + 0.0002, "speed": 6, "heading": 140},
            ]
        mode = "normal"

    if mode == "random_walk":
        points = []
        lat, lng = base_lat, base_lng
        for _ in range(count):
            lat += random.uniform(-0.0012, 0.0012)
            lng += random.uniform(-0.0012, 0.0012)
            points.append({"lat": lat, "lng": lng, "speed": random.randint(10, 60), "heading": random.randint(0, 359)})
        return points

    points = []
    for _ in range(count):
        lat = base_lat + random.uniform(-0.0008, 0.0008)
        lng = base_lng + random.uniform(-0.0008, 0.0008)
        points.append({"lat": lat, "lng": lng, "speed": random.randint(5, 35), "heading": random.randint(0, 359)})
    return points


# ═══════════════════════════ TRACKING MAP ═════════════════════════════

@require_perm("gps.view")
def gps_tracking(request: HttpRequest) -> HttpResponse:
    """Main GPS tracking dashboard — live map with all vehicles."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    vehicles = (
        Vehicle.objects.for_agency(agency)
        .filter(gps_enabled=True)
        .exclude(last_lat__isnull=True)
        .order_by("make", "model")
    )
    zones = GeoZone.objects.for_agency(agency).filter(is_active=True)
    alerts_unresolved = GPSAlert.objects.for_agency(agency).filter(resolved=False).count()

    return render(request, "dashboard/gps/tracking.html", {
        "page_id": "gps_tracking", "breadcrumb": "Suivi GPS",
        "vehicles": vehicles,
        "zones": zones,
        "zones_json": json.dumps([
            {
                "id": z.pk, "name": z.name, "type": z.zone_type,
                "lat": float(z.center_lat), "lng": float(z.center_lng),
                "radius": float(z.radius_km) * 1000,  # meters for Leaflet
                "color": z.color,
            }
            for z in zones
        ]),
        "vehicles_json": json.dumps([
            {
                "id": v.pk,
                "label": str(v),
                "lat": float(v.last_lat),
                "lng": float(v.last_lng),
                "speed": float(v.last_gps_speed) if v.last_gps_speed else 0,
                "updated": v.last_gps_update.isoformat() if v.last_gps_update else "",
                "status": v.status,
            }
            for v in vehicles
        ]),
        "alerts_unresolved": alerts_unresolved,
    })


# ═══════════════════════════ VEHICLE GPS CONFIG ══════════════════════

@require_perm("gps.manage_devices")
def vehicle_gps_config(request: HttpRequest, pk: int) -> HttpResponse:
    """Configure GPS settings for a specific vehicle."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    vehicle = get_object_or_404(Vehicle.objects.for_agency(agency), pk=pk)

    if request.method == "POST" and request.POST.get("action") == "device_create":
        imei = request.POST.get("device_imei", "").strip()[:50]
        provider = request.POST.get("device_provider", "generic")
        display_name = request.POST.get("device_name", "").strip()[:120]
        if not imei:
            messages.error(request, "IMEI requis pour créer un boîtier.")
            return redirect("dashboard:vehicle_gps_config", pk=pk)
        device, created = GPSDevice.objects.get_or_create(
            agency=agency, imei=imei,
            defaults={"provider": provider, "display_name": display_name, "linked_vehicle": vehicle},
        )
        if not created:
            device.provider = provider
            device.display_name = display_name or device.display_name
            if not device.linked_vehicle:
                device.linked_vehicle = vehicle
            device.is_active = True
            device.save(update_fields=["provider", "display_name", "linked_vehicle", "is_active"])
        if vehicle.gps_imei != imei:
            vehicle.gps_imei = imei
            vehicle.save(update_fields=["gps_imei"])
        messages.success(request, "Boîtier GPS enregistré.")
        return redirect("dashboard:vehicle_gps_config", pk=pk)
    if request.method == "POST":
        vehicle.gps_imei = request.POST.get("gps_imei", "").strip()[:50]
        vehicle.gps_ip = request.POST.get("gps_ip", "").strip() or None
        vehicle.gps_source = request.POST.get("gps_source", "device")
        vehicle.gps_enabled = request.POST.get("gps_enabled") == "1"
        vehicle.save(update_fields=[
            "gps_imei", "gps_ip", "gps_source", "gps_enabled",
        ])
        messages.success(request, f"Configuration GPS de {vehicle} mise à jour.")
        return redirect("dashboard:vehicle_gps_config", pk=pk)

    logs = vehicle.gps_logs.all()[:50]
    alerts = vehicle.gps_alerts.all()[:20]
    device = GPSDevice.objects.filter(agency=agency, linked_vehicle=vehicle).first()
    if not device and vehicle.gps_imei:
        device = GPSDevice.objects.filter(agency=agency, imei=vehicle.gps_imei).first()

    return render(request, "dashboard/gps/vehicle_config.html", {
        "page_id": "gps_tracking", "breadcrumb": "Suivi GPS",
        "vehicle": vehicle, "logs": logs, "alerts": alerts,
        "device": device,
        "webhook_url": request.build_absolute_uri(reverse("dashboard:api_gps_update")),
    })


@require_perm("gps.manage_devices")
def contract_gps_config(request: HttpRequest, pk: int) -> HttpResponse:
    """Save GPS configuration for a vehicle directly from the contract detail page.
    Allows admin to toggle GPS, set IMEI/IP, switch between device and phone mode."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    contract = get_object_or_404(Contract.objects.for_agency(agency), pk=pk)
    vehicle = contract.vehicle
    if not vehicle:
        messages.error(request, "Ce contrat n'a pas de véhicule associé.")
        return redirect("dashboard:contract_detail", pk=pk)

    if request.method == "POST":
        gps_enabled = request.POST.get("gps_enabled") == "1"
        gps_source = request.POST.get("gps_source", "device")

        vehicle.gps_enabled = gps_enabled
        vehicle.gps_source = gps_source
        update_fields = ["gps_enabled", "gps_source"]

        if gps_source == "device":
            vehicle.gps_imei = request.POST.get("gps_imei", "").strip()[:50]
            vehicle.gps_ip = request.POST.get("gps_ip", "").strip() or None
            update_fields += ["gps_imei", "gps_ip"]

        vehicle.save(update_fields=update_fields)

        # Auto-fill GPS clause on contract if not already set
        if gps_enabled and not contract.gps_clause:
            try:
                bs = agency.business_settings
                if bs.default_gps_clause:
                    contract.gps_clause = bs.default_gps_clause
                    contract.save(update_fields=["gps_clause"])
            except Exception:
                pass

        mode_label = "boîtier GPS" if gps_source == "device" else "téléphone client"
        if gps_enabled:
            messages.success(request, f"GPS activé en mode {mode_label} pour {vehicle}.")
        else:
            messages.success(request, f"GPS désactivé pour {vehicle}.")

    return redirect("dashboard:contract_detail", pk=pk)


# ═══════════════════════════ GEO ZONES ═══════════════════════════════

@require_perm("gps.manage_zones")
def zone_list(request: HttpRequest) -> HttpResponse:
    """List and manage geofence zones."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    zones = GeoZone.objects.for_agency(agency)
    return render(request, "dashboard/gps/zones.html", {
        "page_id": "gps_tracking", "breadcrumb": "Suivi GPS",
        "zones": zones,
        "zones_json": json.dumps([
            {
                "id": z.pk, "name": z.name, "type": z.zone_type,
                "lat": float(z.center_lat), "lng": float(z.center_lng),
                "radius": float(z.radius_km) * 1000,
                "color": z.color,
            }
            for z in zones
        ]),
    })


@require_perm("gps.manage_zones")
def zone_create(request: HttpRequest) -> HttpResponse:
    """Create a new geofence zone."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    if request.method == "POST":
        try:
            GeoZone.objects.create(
                agency=agency,
                name=request.POST.get("name", "").strip()[:120] or "Zone sans nom",
                zone_type=request.POST.get("zone_type", "restricted"),
                center_lat=Decimal(request.POST.get("center_lat", "0")),
                center_lng=Decimal(request.POST.get("center_lng", "0")),
                radius_km=Decimal(request.POST.get("radius_km", "5")),
                color=request.POST.get("color", "#ef4444").strip()[:20],
                is_active=request.POST.get("is_active") == "1",
                alert_enabled=request.POST.get("alert_enabled") == "1",
            )
            messages.success(request, "Zone créée.")
        except (InvalidOperation, ValueError) as e:
            messages.error(request, f"Erreur de saisie : {e}")
        return redirect("dashboard:gps_zone_list")
    return render(request, "dashboard/gps/zone_form.html", {
        "page_id": "gps_tracking", "breadcrumb": "Suivi GPS",
        "zone": None,
    })


@require_perm("gps.manage_zones")
def zone_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing geofence zone."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    zone = get_object_or_404(GeoZone.objects.for_agency(agency), pk=pk)
    if request.method == "POST":
        try:
            zone.name = request.POST.get("name", "").strip()[:120] or zone.name
            zone.zone_type = request.POST.get("zone_type", zone.zone_type)
            zone.center_lat = Decimal(request.POST.get("center_lat", str(zone.center_lat)))
            zone.center_lng = Decimal(request.POST.get("center_lng", str(zone.center_lng)))
            zone.radius_km = Decimal(request.POST.get("radius_km", str(zone.radius_km)))
            zone.color = request.POST.get("color", zone.color).strip()[:20]
            zone.is_active = request.POST.get("is_active") == "1"
            zone.alert_enabled = request.POST.get("alert_enabled") == "1"
            zone.save()
            messages.success(request, "Zone mise à jour.")
        except (InvalidOperation, ValueError) as e:
            messages.error(request, f"Erreur de saisie : {e}")
        return redirect("dashboard:gps_zone_list")
    return render(request, "dashboard/gps/zone_form.html", {
        "page_id": "gps_tracking", "breadcrumb": "Suivi GPS",
        "zone": zone,
    })


@require_perm("gps.manage_zones")
def zone_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a geofence zone."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    zone = get_object_or_404(GeoZone.objects.for_agency(agency), pk=pk)
    if request.method == "POST":
        zone.delete()
        messages.success(request, "Zone supprimée.")
    return redirect("dashboard:gps_zone_list")


# ═══════════════════════════ ALERTS ══════════════════════════════════

@require_perm("gps.view")
def alert_list(request: HttpRequest) -> HttpResponse:
    """List GPS alerts."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    qs = GPSAlert.objects.for_agency(agency).select_related("vehicle", "zone")
    filter_status = request.GET.get("status", "unresolved")
    filter_type = request.GET.get("type", "")
    vehicle_id = request.GET.get("vehicle")
    if filter_status == "unresolved":
        qs = qs.filter(resolved=False)
    elif filter_status == "resolved":
        qs = qs.filter(resolved=True)
    if filter_type:
        qs = qs.filter(alert_type=filter_type)
    if vehicle_id:
        qs = qs.filter(vehicle_id=vehicle_id)
    alerts = qs[:200]
    return render(request, "dashboard/gps/alerts.html", {
        "page_id": "gps_tracking", "breadcrumb": "Suivi GPS",
        "alerts": alerts, "filter_status": filter_status,
        "filter_type": filter_type,
        "vehicle_id": vehicle_id,
        "vehicles": Vehicle.objects.for_agency(agency).filter(gps_enabled=True),
        "unresolved_count": GPSAlert.objects.for_agency(agency).filter(resolved=False).count(),
    })


@require_perm("gps.manage_zones")
def alert_resolve(request: HttpRequest, pk: int) -> HttpResponse:
    """Resolve a GPS alert."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    alert = get_object_or_404(GPSAlert.objects.for_agency(agency), pk=pk)
    if request.method == "POST" and not alert.resolved:
        alert.resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save(update_fields=["resolved", "resolved_at", "resolved_by"])
        messages.success(request, "Alerte résolue.")
    return redirect("dashboard:gps_alert_list")


# ═══════════════════════════ API ENDPOINTS ════════════════════════════

@csrf_exempt
def api_gps_update(request: HttpRequest) -> JsonResponse:
    """API endpoint for GPS device or client phone to send position updates.
    Accepts POST with JSON body:
    {
        "imei": "...",       // or "vehicle_id": 123
        "lat": 33.5731,
        "lng": -7.5898,
        "speed": 60.5,
        "heading": 180.0,
        "timestamp": "2026-02-10T03:00:00Z"  // optional
    }
    Authentication: token in header X-GPS-Token.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    token = request.headers.get("X-GPS-Token") or request.META.get("HTTP_X_GPS_TOKEN")
    if not token:
        return JsonResponse({"error": "X-GPS-Token required"}, status=401)

    try:
        device = GPSDevice.objects.select_related("agency", "linked_vehicle").get(
            auth_token=token, is_active=True,
        )
    except GPSDevice.DoesNotExist:
        return JsonResponse({"error": "Invalid token"}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return JsonResponse({"error": "lat and lng required"}, status=400)

    imei = data.get("imei", "").strip() or (request.headers.get("X-GPS-IMEI") or request.META.get("HTTP_X_GPS_IMEI", "")).strip()
    if imei and imei != device.imei:
        return JsonResponse({"error": "IMEI mismatch"}, status=403)

    vehicle = device.linked_vehicle
    if not vehicle:
        lookup_imei = imei or device.imei
        vehicle = Vehicle.objects.filter(
            agency=device.agency, gps_imei=lookup_imei, gps_enabled=True,
        ).first()

    if not vehicle:
        return JsonResponse({"error": "Vehicle not found or GPS disabled"}, status=404)

    ts_str = data.get("timestamp")
    if ts_str:
        try:
            from django.utils.dateparse import parse_datetime
            recorded_at = parse_datetime(ts_str)
        except Exception:
            recorded_at = None
    else:
        recorded_at = None

    speed = data.get("speed")
    heading = data.get("heading")
    source = data.get("source", vehicle.gps_source or "device")

    device_ip = request.META.get("REMOTE_ADDR")
    result = _process_gps_update(
        device, lat, lng, speed=speed, heading=heading, recorded_at=recorded_at, source=source, last_ip=device_ip,
    )
    if not result.get("ok"):
        return JsonResponse({"error": result.get("error", "unknown")}, status=400)

    return JsonResponse({
        "ok": True,
        "vehicle_id": result["vehicle"].pk,
        "saved": True,
        "geofence": result["geofence"],
        "ts_server": result["ts_server"].isoformat(),
    })


@login_required
@require_POST
@require_perm("gps.manage_devices")
def api_gps_simulate(request: HttpRequest) -> JsonResponse:
    if not _gps_allowed(request):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)
    if not (request.user.is_superuser or getattr(request.user, "role", "") == "agency_owner"):
        return JsonResponse({"error": "Not allowed"}, status=403)
    agency = _agency(request)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    vehicle_id = data.get("vehicle_id")
    vehicle_id = data.get("vehicle_id")
    if vehicle_id:
        vehicle = Vehicle.objects.for_agency(agency).filter(pk=vehicle_id, gps_enabled=True).first()
    if not vehicle:
        return JsonResponse({"error": "Vehicle not found or GPS disabled"}, status=404)

    device = GPSDevice.objects.filter(agency=agency, linked_vehicle=vehicle).first()
    if not device:
        imei = (vehicle.gps_imei or f"SIM-{vehicle.pk}")[:50]
        device, _ = GPSDevice.objects.get_or_create(
            agency=agency, imei=imei,
            defaults={"provider": "generic", "display_name": f"Simulated {vehicle.pk}", "linked_vehicle": vehicle},
        )
        if device.linked_vehicle_id is None:
            device.linked_vehicle = vehicle
            device.save(update_fields=["linked_vehicle"])

    mode = data.get("mode", "normal")
    count = int(data.get("points") or 10)
    points = _generate_simulated_points(vehicle, mode=mode, count=count)
    alerts_triggered = 0
    zones_violated = set()
    for pt in points:
        res = _process_gps_update(
            device,
            pt["lat"],
            pt["lng"],
            speed=pt.get("speed"),
            heading=pt.get("heading"),
            recorded_at=timezone.now(),
            source="simulate",
        )
        if res.get("ok"):
            alerts_triggered += res["alerts_triggered"]
            zones_violated.update(res["geofence"]["zones_violated"])
    logging.getLogger(__name__).info("[GPS SIM] Vehicle %s simulated with %s points", vehicle.pk, len(points))
    return JsonResponse({
        "status": "ok",
        "points_created": len(points),
        "alerts_triggered": alerts_triggered,
        "zones_violated": sorted(list(zones_violated)),
        "vehicle_updated": True,
    })


@require_perm("gps.manage_devices")
def api_gps_device_create(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    if not (request.user.is_superuser or getattr(request.user, "role", "") == "agency_owner"):
        return JsonResponse({"error": "Not allowed"}, status=403)
    agency = _agency(request)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    imei = (data.get("imei") or "").strip()[:50]
    if not imei:
        return JsonResponse({"error": "imei required"}, status=400)
    provider = data.get("provider", "generic")
    display_name = (data.get("display_name") or "").strip()[:120]
    vehicle_id = data.get("vehicle_id")

    device, created = GPSDevice.objects.get_or_create(
        agency=agency, imei=imei,
        defaults={"provider": provider, "display_name": display_name},
    )
    if vehicle_id:
        vehicle = Vehicle.objects.for_agency(agency).filter(pk=vehicle_id).first()
        if vehicle:
            device.linked_vehicle = vehicle
            if not vehicle.gps_imei:
                vehicle.gps_imei = imei
                vehicle.save(update_fields=["gps_imei"])
    device.provider = provider
    device.display_name = display_name or device.display_name
    device.is_active = True
    device.save(update_fields=["provider", "display_name", "linked_vehicle", "is_active"])

    return JsonResponse({
        "ok": True,
        "device_id": device.pk,
        "vehicle_id": device.linked_vehicle_id,
        "auth_token": device.auth_token,
        "imei": device.imei,
    })


def _check_geofences(vehicle, lat, lng, recorded_at=None):
    """Check all agency zones and create alerts if needed."""
    zones = GeoZone.objects.filter(agency=vehicle.agency, alert_enabled=True, is_active=True)
    events_count = 0
    alerts_triggered = 0
    zones_violated = set()
    active_contract = None
    now = recorded_at or timezone.now()

    for zone in zones:
        inside = zone.contains_point(lat, lng)
        state, created = VehicleZoneState.objects.get_or_create(
            agency=vehicle.agency, vehicle=vehicle, zone=zone,
            defaults={"is_inside": inside, "last_changed_at": now if inside else None},
        )
        if created and inside:
            GeofenceEvent.objects.create(
                agency=vehicle.agency,
                vehicle=vehicle,
                zone=zone,
                event_type="enter",
                occurred_at=now,
                lat=Decimal(str(lat)),
                lng=Decimal(str(lng)),
                payload={"source": "gps"},
            )
            if active_contract is None:
                active_contract = Contract.vehicle_has_active_contract(vehicle)
            GPSAlert.objects.create(
                agency=vehicle.agency,
                vehicle=vehicle,
                zone=zone,
                contract=active_contract,
                alert_type="zone_enter",
                lat=Decimal(str(lat)),
                lng=Decimal(str(lng)),
                message=f"{vehicle} est entré dans la zone « {zone.name} »",
            )
            events_count += 1
            alerts_triggered += 1
        elif not created and inside != state.is_inside:
            state.is_inside = inside
            state.last_changed_at = now
            state.save(update_fields=["is_inside", "last_changed_at"])
            event_type = "enter" if inside else "exit"
            GeofenceEvent.objects.create(
                agency=vehicle.agency,
                vehicle=vehicle,
                zone=zone,
                event_type=event_type,
                occurred_at=now,
                lat=Decimal(str(lat)),
                lng=Decimal(str(lng)),
                payload={"source": "gps"},
            )
            if active_contract is None:
                active_contract = Contract.vehicle_has_active_contract(vehicle)
            alert_type = "zone_enter" if inside else "zone_exit"
            GPSAlert.objects.create(
                agency=vehicle.agency,
                vehicle=vehicle,
                zone=zone,
                contract=active_contract,
                alert_type=alert_type,
                lat=Decimal(str(lat)),
                lng=Decimal(str(lng)),
                message=f"{vehicle} {'est entré' if inside else 'est sorti'} de la zone « {zone.name} »",
            )
            events_count += 1
            alerts_triggered += 1

        if zone.zone_type == "restricted" and inside:
            throttled = state.last_violation_at and (now - state.last_violation_at) < timedelta(minutes=10)
            if not throttled or created:
                GeofenceEvent.objects.create(
                    agency=vehicle.agency,
                    vehicle=vehicle,
                    zone=zone,
                    event_type="violation",
                    occurred_at=now,
                    lat=Decimal(str(lat)),
                    lng=Decimal(str(lng)),
                    payload={"source": "gps"},
                )
                if active_contract is None:
                    active_contract = Contract.vehicle_has_active_contract(vehicle)
                GPSAlert.objects.create(
                    agency=vehicle.agency,
                    vehicle=vehicle,
                    zone=zone,
                    contract=active_contract,
                    alert_type="zone_violation",
                    lat=Decimal(str(lat)),
                    lng=Decimal(str(lng)),
                    message=f"{vehicle} est en zone interdite « {zone.name} »",
                )
                state.last_violation_at = now
                state.save(update_fields=["last_violation_at"])
                events_count += 1
                alerts_triggered += 1
                zones_violated.add(zone.name)

    return {"events_created": events_count, "alerts_triggered": alerts_triggered, "zones_violated": sorted(list(zones_violated))}


# ═══════════════════════════ MAPS HUB (Premium) ══════════════════════

@require_perm("gps.view")
def maps_hub(request: HttpRequest) -> HttpResponse:
    """Premium interactive maps hub — MapLibre GL JS with AI features."""
    if not _gps_allowed(request):
        return HttpResponseForbidden("GPS non disponible pour ce plan.")
    agency = _agency(request)
    vehicles = (
        Vehicle.objects.for_agency(agency)
        .filter(gps_enabled=True)
        .order_by("make", "model")
    )
    vehicles_with_pos = [v for v in vehicles if v.last_lat is not None]
    zones = GeoZone.objects.for_agency(agency).filter(is_active=True)
    alerts_unresolved = GPSAlert.objects.for_agency(agency).filter(resolved=False).count()
    recent_alerts = GPSAlert.objects.for_agency(agency).filter(resolved=False).select_related("vehicle", "zone").order_by("-created_at")[:10]

    # Active contracts for vehicle info
    active_contracts = Contract.objects.filter(
        agency=agency, status="active",
    ).select_related("vehicle", "client_account")
    contract_map = {c.vehicle_id: c for c in active_contracts if c.vehicle_id}

    vehicles_json = []
    for v in vehicles_with_pos:
        c = contract_map.get(v.pk)
        vehicles_json.append({
            "id": v.pk,
            "label": str(v),
            "lat": float(v.last_lat),
            "lng": float(v.last_lng),
            "speed": float(v.last_gps_speed) if v.last_gps_speed else 0,
            "updated": v.last_gps_update.isoformat() if v.last_gps_update else "",
            "status": v.status,
            "source": v.gps_source or "device",
            "client": str(c.client_account) if c else None,
            "contract_id": c.pk if c else None,
            "imei": v.gps_imei or "",
        })

    zones_json = [
        {
            "id": z.pk, "name": z.name, "type": z.zone_type,
            "lat": float(z.center_lat), "lng": float(z.center_lng),
            "radius": float(z.radius_km) * 1000,
            "color": z.color,
        }
        for z in zones
    ]

    alerts_json = [
        {
            "id": a.pk,
            "type": a.alert_type,
            "message": a.message,
            "vehicle": str(a.vehicle),
            "lat": float(a.lat) if a.lat else None,
            "lng": float(a.lng) if a.lng else None,
            "created": a.created_at.isoformat(),
            "zone": a.zone.name if a.zone else None,
        }
        for a in recent_alerts
    ]

    return render(request, "dashboard/gps/maps_hub.html", {
        "page_id": "maps_hub", "breadcrumb": "Carte intelligente",
        "vehicles": vehicles,
        "vehicles_with_pos": vehicles_with_pos,
        "zones": zones,
        "alerts_unresolved": alerts_unresolved,
        "vehicles_json": json.dumps(vehicles_json),
        "zones_json": json.dumps(zones_json),
        "alerts_json": json.dumps(alerts_json),
    })


@require_perm("gps.view")
def api_maps_ai_analyze(request: HttpRequest) -> JsonResponse:
    """AI-powered vehicle behavior analysis — returns insights for a vehicle."""
    if not _gps_allowed(request):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)
    agency = _agency(request)
    vehicle_id = request.GET.get("vehicle_id")
    if not vehicle_id:
        return JsonResponse({"error": "vehicle_id required"}, status=400)

    vehicle = get_object_or_404(Vehicle.objects.for_agency(agency), pk=vehicle_id)
    hours = int(request.GET.get("hours", 24))
    since = timezone.now() - timedelta(hours=hours)

    logs = GPSPositionLog.objects.filter(
        vehicle=vehicle, recorded_at__gte=since,
    ).order_by("recorded_at")

    if not logs.exists():
        return JsonResponse({
            "vehicle": str(vehicle),
            "insights": [],
            "stats": {},
            "risk_score": 0,
        })

    log_list = list(logs.values("lat", "lng", "speed", "recorded_at"))

    # Compute stats
    speeds = [float(log_item["speed"]) for log_item in log_list if log_item["speed"]]
    total_points = len(log_list)
    avg_speed = sum(speeds) / len(speeds) if speeds else 0
    max_speed = max(speeds) if speeds else 0
    moving_points = len([s for s in speeds if s > 5])
    idle_points = total_points - moving_points

    # Time analysis
    first_ts = log_list[0]["recorded_at"]
    last_ts = log_list[-1]["recorded_at"]
    duration_h = (last_ts - first_ts).total_seconds() / 3600 if total_points > 1 else 0

    # Distance estimation (haversine simplified)
    total_km = 0
    for i in range(1, len(log_list)):
        lat1, lng1 = float(log_list[i-1]["lat"]), float(log_list[i-1]["lng"])
        lat2, lng2 = float(log_list[i]["lat"]), float(log_list[i]["lng"])
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        total_km += 6371 * c

    # Generate AI insights
    insights = []

    if max_speed > 120:
        insights.append({"type": "danger", "icon": "speed", "text": f"Vitesse excessive détectée : {max_speed:.0f} km/h"})
    elif max_speed > 80:
        insights.append({"type": "warning", "icon": "speed", "text": f"Vitesse élevée : {max_speed:.0f} km/h max"})

    if idle_points > total_points * 0.7 and total_points > 10:
        insights.append({"type": "info", "icon": "parking", "text": f"Véhicule principalement à l'arrêt ({idle_points}/{total_points} points)"})

    if duration_h > 0 and total_km / max(duration_h, 0.1) > 100:
        insights.append({"type": "warning", "icon": "route", "text": f"Conduite intensive : {total_km:.1f} km en {duration_h:.1f}h"})

    if total_km > 300:
        insights.append({"type": "info", "icon": "distance", "text": f"Long trajet : {total_km:.1f} km parcourus"})

    # Night driving check
    night_points = 0
    for log_item in log_list:
        h = log_item["recorded_at"].hour
        if h >= 23 or h < 5:
            night_points += 1
    if night_points > total_points * 0.3 and night_points > 5:
        insights.append({"type": "warning", "icon": "night", "text": f"Conduite nocturne significative ({night_points} points entre 23h-5h)"})

    # Risk score (0-100)
    risk = 0
    if max_speed > 130:
        risk += 40
    elif max_speed > 100:
        risk += 20
    elif max_speed > 80:
        risk += 10
    if night_points > 10:
        risk += 15
    if total_km > 500:
        risk += 10
    alerts_count = GPSAlert.objects.filter(vehicle=vehicle, resolved=False).count()
    risk += min(alerts_count * 10, 30)
    risk = min(risk, 100)

    return JsonResponse({
        "vehicle": str(vehicle),
        "stats": {
            "total_points": total_points,
            "avg_speed": round(avg_speed, 1),
            "max_speed": round(max_speed, 1),
            "total_km": round(total_km, 1),
            "duration_h": round(duration_h, 1),
            "moving_pct": round(moving_points / max(total_points, 1) * 100),
            "idle_pct": round(idle_points / max(total_points, 1) * 100),
        },
        "insights": insights,
        "risk_score": risk,
        "alerts_active": alerts_count,
    })


@require_perm("gps.view")
def api_maps_heatmap(request: HttpRequest) -> JsonResponse:
    """Return GPS position data for heatmap visualization."""
    if not _gps_allowed(request):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)
    agency = _agency(request)
    hours = int(request.GET.get("hours", 48))
    since = timezone.now() - timedelta(hours=hours)
    vehicle_id = request.GET.get("vehicle_id")

    qs = GPSPositionLog.objects.filter(
        vehicle__agency=agency,
        vehicle__gps_enabled=True,
        recorded_at__gte=since,
    )
    if vehicle_id:
        qs = qs.filter(vehicle_id=vehicle_id)

    # Sample max 2000 points for performance
    logs = qs.order_by("recorded_at")[:2000]
    points = [
        [float(log.lat), float(log.lng), float(log.speed) if log.speed else 0]
        for log in logs
    ]
    return JsonResponse({"points": points, "count": len(points)})


@require_perm("gps.view")
def api_gps_positions(request: HttpRequest) -> JsonResponse:
    """AJAX endpoint — return current positions of all GPS-enabled vehicles."""
    if not _gps_allowed(request):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)
    agency = _agency(request)
    vehicles = (
        Vehicle.objects.for_agency(agency)
        .filter(gps_enabled=True)
        .exclude(last_lat__isnull=True)
    )
    data = [
        {
            "id": v.pk,
            "label": str(v),
            "lat": float(v.last_lat),
            "lng": float(v.last_lng),
            "speed": float(v.last_gps_speed) if v.last_gps_speed else 0,
            "updated": v.last_gps_update.isoformat() if v.last_gps_update else "",
            "status": v.status,
            "source": v.gps_source or "device",
        }
        for v in vehicles
    ]
    unresolved = GPSAlert.objects.for_agency(agency).filter(resolved=False).count()
    return JsonResponse({"vehicles": data, "alerts_unresolved": unresolved})


@require_perm("gps.view")
def api_vehicle_trail(request: HttpRequest, pk: int) -> JsonResponse:
    """AJAX endpoint — return recent GPS trail for a vehicle."""
    if not _gps_allowed(request):
        return JsonResponse({"error": "GPS non disponible pour ce plan."}, status=403)
    agency = _agency(request)
    vehicle = get_object_or_404(Vehicle.objects.for_agency(agency), pk=pk)
    hours = int(request.GET.get("hours", 24))
    since = timezone.now() - timedelta(hours=hours)
    logs = GPSPositionLog.objects.filter(
        vehicle=vehicle, recorded_at__gte=since,
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
    return JsonResponse({"vehicle": str(vehicle), "trail": trail})
