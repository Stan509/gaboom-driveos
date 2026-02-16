from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from agencies.models_access import AgencyAccess


PLAN_CONFIGS = {
    "starter": {
        "code": "starter",
        "name": "Starter",
        "price": 59,
        "currency": "USD",
        "max_agencies": 1,
        "max_users": 3,
        "max_vehicles": 20,
        "features": {
            "public_site": True,
            "online_booking": True,
            "gps_tracking": False,
            "marketing_tools": False,
            "loyalty": False,
            "client_portal": False,
            "priority_support": False,
            "workflows": False,
            "integrations": False,
        },
    },
    "business": {
        "code": "business",
        "name": "Business",
        "price": 99,
        "currency": "USD",
        "max_agencies": 3,
        "max_users": 0,
        "max_vehicles": 0,
        "features": {
            "public_site": True,
            "online_booking": True,
            "gps_tracking": True,
            "marketing_tools": True,
            "loyalty": True,
            "client_portal": True,
            "priority_support": True,
            "workflows": False,
            "integrations": False,
        },
    },
    "enterprise": {
        "code": "enterprise",
        "name": "Enterprise",
        "price": 199,
        "currency": "USD",
        "max_agencies": 0,
        "max_users": 0,
        "max_vehicles": 0,
        "features": {
            "public_site": True,
            "online_booking": True,
            "gps_tracking": True,
            "marketing_tools": True,
            "loyalty": True,
            "client_portal": True,
            "priority_support": True,
            "workflows": True,
            "integrations": True,
        },
    },
}


def get_plan_config(plan_code):
    return PLAN_CONFIGS.get(plan_code) or PLAN_CONFIGS["starter"]


def apply_plan_to_access(access, plan_code):
    plan = get_plan_config(plan_code)
    access.plan_code = plan["code"]
    access.plan_name = plan["name"]
    access.plan_price = plan["price"]
    access.plan_currency = plan["currency"]
    access.max_agencies = plan["max_agencies"]
    access.max_users = plan["max_users"]
    access.max_vehicles = plan["max_vehicles"]
    access.plan_features = plan["features"]
    access.save(update_fields=[
        "plan_code", "plan_name", "plan_price", "plan_currency",
        "max_agencies", "max_users", "max_vehicles", "plan_features",
        "updated_at",
    ])
    return access


def ensure_plan(access):
    plan = get_plan_config(access.plan_code)
    if (
        access.plan_name != plan["name"]
        or access.plan_price != plan["price"]
        or access.plan_currency != plan["currency"]
        or access.max_agencies != plan["max_agencies"]
        or access.max_users != plan["max_users"]
        or access.max_vehicles != plan["max_vehicles"]
        or access.plan_features != plan["features"]
    ):
        apply_plan_to_access(access, access.plan_code)
    return access


def get_agency_access(agency):
    """Get or create AgencyAccess for an agency."""
    now = timezone.now()
    access, _created = AgencyAccess.objects.get_or_create(
        agency=agency,
        defaults={
            "status": "trial",
            "trial_started_at": agency.created_at or now,
            "access_ends_at": (agency.created_at or now) + timedelta(days=3),
        },
    )
    if not access.plan_code:
        apply_plan_to_access(access, "starter")
    else:
        ensure_plan(access)
    return access


def sync_access(access):
    """If deadline passed and not already suspended → suspend. Never auto-reactivate."""
    ensure_plan(access)
    if access.status in ("trial", "active") and access.is_expired:
        access.status = "suspended"
        access.suspended_reason = "Expiration automatique"
        access.save(update_fields=["status", "suspended_reason", "updated_at"])
        return True
    return False


@transaction.atomic
def renew_access(access, days=30, by_user=None, reason=""):
    """Renew access for N days. status → active, access_ends_at = now + days."""
    now = timezone.now()
    access.status = "active"
    access.access_ends_at = now + timedelta(days=days)
    access.suspended_reason = ""
    access.save(update_fields=["status", "access_ends_at", "suspended_reason", "updated_at"])
    return access


@transaction.atomic
def suspend_access(access, reason="", by_user=None):
    """Manually suspend an agency."""
    access.status = "suspended"
    access.suspended_reason = reason or "Suspension manuelle"
    access.save(update_fields=["status", "suspended_reason", "updated_at"])
    return access


@transaction.atomic
def grant_bonus_days(access, days=7, by_user=None, reason=""):
    """Add bonus days to current deadline. If suspended, reactivate."""
    delta = timedelta(days=days)
    if access.status == "suspended":
        access.status = "active"
        access.access_ends_at = timezone.now() + delta
        access.suspended_reason = ""
    else:
        access.access_ends_at = access.access_ends_at + delta
    access.save(update_fields=["status", "access_ends_at", "suspended_reason", "updated_at"])
    return access


# ═══════════════════════════════════════════════════════════════════════
# PAYPAL HYBRID BILLING
# ═══════════════════════════════════════════════════════════════════════

@transaction.atomic
def switch_to_paypal(access, subscription_id, by_user=None):
    """Switch agency from manual to PayPal automatic billing."""
    now = timezone.now()
    access.billing_mode = "paypal"
    access.paypal_subscription_id = subscription_id
    access.paypal_status = "active"
    access.status = "active"
    access.access_ends_at = now + timedelta(days=30)
    access.suspended_reason = ""
    access.needs_admin_attention = True
    access.admin_alert_code = "manual_to_paypal"
    access.admin_alert_message = "L'agence est passée en paiement PayPal automatique."
    access.billing_last_changed_reason = f"Switch to PayPal (sub: {subscription_id})"
    access.save(update_fields=[
        "billing_mode", "paypal_subscription_id", "paypal_status",
        "status", "access_ends_at", "suspended_reason",
        "needs_admin_attention", "admin_alert_code", "admin_alert_message",
        "billing_last_changed_reason", "billing_last_changed_at", "updated_at",
    ])
    return access


@transaction.atomic
def switch_to_manual(access, reason="", by_user=None):
    """Switch agency from PayPal to manual billing (e.g. after cancellation)."""
    now = timezone.now()
    access.billing_mode = "manual"
    access.paypal_status = "cancelled"
    access.paypal_cancelled_at = now
    access.needs_admin_attention = True
    access.admin_alert_code = "paypal_to_manual"
    access.admin_alert_message = f"Abonnement PayPal annulé. Passage en mode manuel. Raison: {reason}"
    access.billing_last_changed_reason = f"Switch to manual: {reason}"
    access.save(update_fields=[
        "billing_mode", "paypal_status", "paypal_cancelled_at",
        "needs_admin_attention", "admin_alert_code", "admin_alert_message",
        "billing_last_changed_reason", "billing_last_changed_at", "updated_at",
    ])
    return access


@transaction.atomic
def paypal_event_update(access, event_type, event_payload=None):
    """Process a PayPal webhook event and update access accordingly."""
    now = timezone.now()
    access.paypal_last_event_at = now

    if event_type in ("PAYMENT.SALE.COMPLETED", "BILLING.SUBSCRIPTION.ACTIVATED"):
        access.paypal_status = "active"
        access.status = "active"
        access.access_ends_at = now + timedelta(days=30)
        access.suspended_reason = ""
        access.needs_admin_attention = False
        access.admin_alert_code = "none"
        access.admin_alert_message = ""
        access.save(update_fields=[
            "paypal_status", "paypal_last_event_at", "status",
            "access_ends_at", "suspended_reason",
            "needs_admin_attention", "admin_alert_code", "admin_alert_message",
            "updated_at",
        ])

    elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        access.paypal_status = "suspended"
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_payment_failed"
        access.admin_alert_message = "Paiement PayPal échoué. L'agence risque d'être bloquée."
        access.save(update_fields=[
            "paypal_status", "paypal_last_event_at",
            "needs_admin_attention", "admin_alert_code", "admin_alert_message",
            "updated_at",
        ])

    elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
        access.paypal_status = "suspended"
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_payment_failed"
        access.admin_alert_message = "Abonnement PayPal suspendu par PayPal."
        access.save(update_fields=[
            "paypal_status", "paypal_last_event_at",
            "needs_admin_attention", "admin_alert_code", "admin_alert_message",
            "updated_at",
        ])

    elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
        access.paypal_last_event_at = now
        access.save(update_fields=["paypal_last_event_at", "updated_at"])
        switch_to_manual(access, reason="cancelled_by_agency")

    elif event_type == "BILLING.SUBSCRIPTION.EXPIRED":
        access.paypal_status = "expired"
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_cancelled"
        access.admin_alert_message = "Abonnement PayPal expiré. Renouvellement manuel requis."
        access.save(update_fields=[
            "paypal_status", "paypal_last_event_at",
            "needs_admin_attention", "admin_alert_code", "admin_alert_message",
            "updated_at",
        ])

    else:
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_status_unknown"
        access.admin_alert_message = f"Événement PayPal inconnu: {event_type}"
        access.save(update_fields=[
            "paypal_last_event_at",
            "needs_admin_attention", "admin_alert_code", "admin_alert_message",
            "updated_at",
        ])

    return access


def dismiss_admin_alert(access):
    """Mark admin alert as handled."""
    access.needs_admin_attention = False
    access.admin_alert_code = "none"
    access.admin_alert_message = ""
    access.save(update_fields=[
        "needs_admin_attention", "admin_alert_code", "admin_alert_message", "updated_at",
    ])
    return access
