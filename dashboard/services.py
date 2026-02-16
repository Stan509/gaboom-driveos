"""
Dashboard services — business logic separated from views.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count
from django.utils import timezone


def compute_marketing_stats(agency):
    """Compute dynamic marketing KPIs for an agency. No extra table needed."""
    from agencies.models import ReservationRequest

    now = timezone.now()
    d30 = now - timedelta(days=30)

    qs = ReservationRequest.objects.filter(agency=agency)
    total = qs.count()
    confirmed = qs.filter(status="confirmed").count()
    last30 = qs.filter(created_at__gte=d30)
    last30_confirmed = last30.filter(status="confirmed")

    # Conversion rate
    total_30 = last30.count()
    confirmed_30 = last30_confirmed.count()
    conversion_rate = round(confirmed_30 / total_30 * 100, 1) if total_30 else 0

    # Revenue last 30 days (estimated)
    revenue_30 = Decimal("0")
    for r in last30_confirmed:
        revenue_30 += r.estimated_total or 0

    # Negotiation success rate
    nego_qs = qs.exclude(negotiation_status="none")
    nego_total = nego_qs.count()
    nego_accepted = nego_qs.filter(negotiation_status="accepted").count()
    negotiation_success_rate = round(nego_accepted / nego_total * 100, 1) if nego_total else 0
    negotiation_rate = round(nego_total / total * 100, 1) if total else 0

    # Avg price per booking
    avg_price = last30_confirmed.aggregate(
        avg=Avg("daily_price_accepted"),
    )["avg"] or Decimal("0")

    # Top vehicle
    top_vehicle_data = (
        last30.values("vehicle__make", "vehicle__model", "vehicle__pk")
        .annotate(cnt=Count("pk"))
        .order_by("-cnt")
        .first()
    )
    top_vehicle = None
    if top_vehicle_data:
        top_vehicle = {
            "name": f"{top_vehicle_data['vehicle__make']} {top_vehicle_data['vehicle__model']}",
            "pk": top_vehicle_data["vehicle__pk"],
            "count": top_vehicle_data["cnt"],
        }

    # Most active day
    from django.db.models.functions import ExtractWeekDay
    day_data = (
        qs.annotate(wd=ExtractWeekDay("created_at"))
        .values("wd")
        .annotate(cnt=Count("pk"))
        .order_by("-cnt")
        .first()
    )
    DAY_NAMES = {1: "Dimanche", 2: "Lundi", 3: "Mardi", 4: "Mercredi",
                 5: "Jeudi", 6: "Vendredi", 7: "Samedi"}
    most_active_day = DAY_NAMES.get(day_data["wd"], "—") if day_data else "—"

    # Repeat customer rate
    client_ids_with_bookings = (
        qs.filter(client_account__isnull=False)
        .values("client_account")
        .annotate(cnt=Count("pk"))
    )
    total_clients = client_ids_with_bookings.count()
    repeat_clients = client_ids_with_bookings.filter(cnt__gte=2).count()
    repeat_customer_rate = round(repeat_clients / total_clients * 100, 1) if total_clients else 0

    return {
        "conversion_rate": conversion_rate,
        "revenue_last_30_days": revenue_30,
        "negotiation_success_rate": negotiation_success_rate,
        "negotiation_rate": negotiation_rate,
        "avg_price_per_booking": round(avg_price, 2),
        "top_vehicle": top_vehicle,
        "most_active_day": most_active_day,
        "repeat_customer_rate": repeat_customer_rate,
        "total_reservations": total,
        "confirmed_reservations": confirmed,
        "total_30": total_30,
        "confirmed_30": confirmed_30,
    }


def compute_recommended_price(vehicle):
    """
    Smart pricing — compute recommended price for a vehicle.
    No external API. Pure internal data analysis.
    """
    from agencies.models import ReservationRequest

    d30 = timezone.now() - timedelta(days=30)
    qs = ReservationRequest.objects.filter(vehicle=vehicle, created_at__gte=d30)

    bookings_30 = qs.count()
    nego_qs = qs.exclude(negotiation_status="none")
    nego_count = nego_qs.count()

    current_price = vehicle.daily_price or Decimal("0")
    if current_price == 0:
        return {
            "recommended_price": Decimal("0"),
            "confidence_score": 0,
            "message": "Prix actuel non défini.",
            "direction": "neutral",
        }

    # Demand level (0-100)
    demand = min(bookings_30 * 10, 100)

    # Negotiation rate
    nego_rate = (nego_count / bookings_30 * 100) if bookings_30 else 0

    # Popularity score
    all_vehicles_bookings = (
        ReservationRequest.objects.filter(
            agency=vehicle.agency, created_at__gte=d30,
        ).values("vehicle").annotate(cnt=Count("pk"))
    )
    max_bookings = max((v["cnt"] for v in all_vehicles_bookings), default=1)
    popularity = (bookings_30 / max_bookings * 100) if max_bookings else 0

    # Compute adjustment
    adjustment = Decimal("0")
    message = ""
    direction = "neutral"

    if demand >= 70 and nego_rate < 30:
        # High demand, low negotiation → raise price
        pct = min(Decimal("15"), Decimal(str(demand / 10)))
        adjustment = (current_price * pct / 100).quantize(Decimal("0.01"))
        message = f"Forte demande ({bookings_30} réservations/30j). Augmentation suggérée de {pct}%."
        direction = "up"
    elif demand < 30 and bookings_30 > 0:
        # Low demand → lower price
        pct = min(Decimal("10"), Decimal("5") + Decimal(str((100 - demand) / 20)))
        adjustment = -(current_price * pct / 100).quantize(Decimal("0.01"))
        message = f"Demande faible ({bookings_30} réservations/30j). Réduction suggérée de {pct}%."
        direction = "down"
    elif nego_rate > 40:
        # High negotiation → price may be too high
        avg_offer = nego_qs.aggregate(avg=Avg("daily_price_offer"))["avg"]
        if avg_offer:
            diff = current_price - avg_offer
            adjustment = -(diff * Decimal("0.5")).quantize(Decimal("0.01"))
            message = f"Taux de négociation élevé ({nego_rate:.0f}%). Ajustement vers le marché."
            direction = "down"
        else:
            message = "Beaucoup de négociations mais données insuffisantes."
    else:
        message = "Prix actuel bien positionné."

    recommended = max(current_price + adjustment, Decimal("1"))

    # Confidence score (0-100)
    confidence = min(int(bookings_30 * 5 + popularity * 0.3), 100)

    return {
        "recommended_price": recommended.quantize(Decimal("0.01")),
        "confidence_score": confidence,
        "message": message,
        "direction": direction,
        "demand_level": demand,
        "popularity_score": round(popularity, 1),
        "negotiation_rate": round(nego_rate, 1),
        "bookings_30": bookings_30,
    }
