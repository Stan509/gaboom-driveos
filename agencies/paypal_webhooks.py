import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from agencies.models_access import AgencyAccess
from agencies.services import paypal_event_update
from core.models_admin_alert import AdminAlert
from core.models_paypal_event import PayPalEvent
from core.models_paypal_subscription import PayPalSubscription
from core.services_paypal_api import verify_webhook_signature
from core.services_platform import get_paypal_config

logger = logging.getLogger(__name__)

# PayPal event types we handle
HANDLED_EVENTS = {
    "PAYMENT.SALE.COMPLETED",
    "BILLING.SUBSCRIPTION.ACTIVATED",
    "BILLING.SUBSCRIPTION.CANCELLED",
    "BILLING.SUBSCRIPTION.SUSPENDED",
    "BILLING.SUBSCRIPTION.EXPIRED",
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
}


@csrf_exempt
@require_POST
def paypal_webhook(request):
    """
    Receive PayPal webhook events.
    POST /webhooks/paypal/

    Reads config from PlatformSettings via get_paypal_config().
    Logs every event to PayPalEvent for the SuperAdmin webhooks log.
    Verifies signature if enabled.
    Updates PayPalSubscription detail record.
    Creates AdminAlert for events requiring attention.
    """
    # ── Parse payload ───────────────────────────────────────────────
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        logger.warning("PayPal webhook: invalid JSON body")
        return HttpResponseBadRequest("Invalid JSON")

    event_type = payload.get("event_type", "")
    event_id = payload.get("id", "")
    resource = payload.get("resource", {})

    # ── Idempotence: check if event already processed ─────────────────
    if PayPalEvent.objects.filter(event_id=event_id).exists():
        logger.info(f"PayPal webhook: event {event_id} already processed, skipping")
        return HttpResponse("OK", status=200)

    # ── Signature verification ──────────────────────────────────────
    config = get_paypal_config()
    verified = False
    if config["webhook_verify"] and config["webhook_id"]:
        pp_headers = {
            "PAYPAL-AUTH-ALGO": request.META.get("HTTP_PAYPAL_AUTH_ALGO", ""),
            "PAYPAL-CERT-URL": request.META.get("HTTP_PAYPAL_CERT_URL", ""),
            "PAYPAL-TRANSMISSION-ID": request.META.get("HTTP_PAYPAL_TRANSMISSION_ID", ""),
            "PAYPAL-TRANSMISSION-SIG": request.META.get("HTTP_PAYPAL_TRANSMISSION_SIG", ""),
            "PAYPAL-TRANSMISSION-TIME": request.META.get("HTTP_PAYPAL_TRANSMISSION_TIME", ""),
        }
        verified = verify_webhook_signature(pp_headers, request.body, config)
        if not verified:
            logger.warning("PayPal webhook: signature verification FAILED for event %s", event_id)
    else:
        verified = True  # verification not enabled, treat as trusted

    # ── Extract subscription_id ─────────────────────────────────────
    subscription_id = (
        resource.get("billing_agreement_id")  # PAYMENT.SALE.COMPLETED
        or resource.get("id")                  # BILLING.SUBSCRIPTION.*
        or ""
    )

    # ── Find matching AgencyAccess ──────────────────────────────────
    agency_name = ""
    access = None
    if subscription_id:
        try:
            access = AgencyAccess.objects.select_related("agency").get(
                paypal_subscription_id=subscription_id,
            )
            agency_name = access.agency.name
        except AgencyAccess.DoesNotExist:
            # Also try via PayPalSubscription
            try:
                pp_sub = PayPalSubscription.objects.select_related(
                    "access__agency"
                ).get(paypal_subscription_id=subscription_id)
                access = pp_sub.access
                agency_name = access.agency.name
            except PayPalSubscription.DoesNotExist:
                logger.warning(
                    "PayPal webhook: no AgencyAccess for subscription_id=%s (event=%s)",
                    subscription_id, event_type,
                )

    # ── Log event to DB ─────────────────────────────────────────────
    PayPalEvent.objects.create(
        event_id=event_id,
        event_type=event_type,
        subscription_id=subscription_id,
        resource_id=resource.get("id", ""),
        agency_name=agency_name,
        payload=payload,
        processed=access is not None,
        verified=verified,
    )

    # ── Update last_webhook_received_at ─────────────────────────────
    try:
        from core.models_platform import PlatformSettings
        ps = PlatformSettings.get()
        ps.last_webhook_received_at = timezone.now()
        ps.save(update_fields=["last_webhook_received_at", "updated_at"])
    except Exception:
        pass

    # ── Process event ───────────────────────────────────────────────
    if access:
        logger.info(
            "PayPal webhook: event=%s subscription=%s agency=%s",
            event_type, subscription_id, access.agency_id,
        )
        paypal_event_update(access, event_type, event_payload=payload)

        # ── Update PayPalSubscription detail ────────────────────────
        _update_paypal_subscription(access, event_type, resource)

        # ── Update AgencyAccess status based on event ───────────────
        _update_agency_access_status(access, event_type, resource)

        # ── Create AdminAlert for attention-requiring events ────────
        _create_alert_if_needed(access, event_type)

    elif not subscription_id:
        logger.warning("PayPal webhook: no subscription_id found in event %s", event_type)

    return HttpResponse("OK", status=200)


def _update_paypal_subscription(access, event_type, resource):
    """Update the PayPalSubscription detail record based on webhook event."""
    now = timezone.now()
    try:
        pp_sub = PayPalSubscription.objects.get(access=access)
    except PayPalSubscription.DoesNotExist:
        return

    pp_sub.last_event_at = now

    if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
        pp_sub.status = "ACTIVE"
        pp_sub.payer_email = resource.get("subscriber", {}).get("email_address", pp_sub.payer_email)
        billing_info = resource.get("billing_info", {})
        next_billing = billing_info.get("next_billing_time", "")
        if next_billing:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(next_billing)
            if dt:
                pp_sub.next_billing_time = dt

    elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
        pp_sub.status = "CANCELLED"
        pp_sub.cancelled_at = now

    elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
        pp_sub.status = "SUSPENDED"

    elif event_type == "BILLING.SUBSCRIPTION.EXPIRED":
        pp_sub.status = "EXPIRED"

    elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        pp_sub.last_error = f"Payment failed at {now.isoformat()}"

    elif event_type == "PAYMENT.SALE.COMPLETED":
        pp_sub.status = "ACTIVE"
        billing_info = resource.get("billing_info", {})
        next_billing = billing_info.get("next_billing_time", "")
        if next_billing:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(next_billing)
            if dt:
                pp_sub.next_billing_time = dt

    pp_sub.save()


def _update_agency_access_status(access, event_type, resource):
    """Update AgencyAccess status based on webhook event."""
    now = timezone.now()
    
    if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
        # Activate agency access
        access.status = "active"
        access.billing_mode = "paypal"
        access.paypal_status = "active"
        access.paypal_last_event_at = now
        access.needs_admin_attention = False
        access.admin_alert_code = "none"
        access.admin_alert_message = ""
        access.billing_last_changed_reason = f"PayPal subscription ACTIVATED at {now}"
        
        # Extend access period (e.g., 30 days from now)
        from datetime import timedelta
        access.access_ends_at = now + timedelta(days=30)
        
    elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
        # Suspend agency access
        access.status = "suspended"
        access.billing_mode = "paypal"
        access.paypal_status = "cancelled"
        access.paypal_last_event_at = now
        access.paypal_cancelled_at = now
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_cancelled"
        access.admin_alert_message = f"PayPal subscription CANCELLED at {now}"
        access.billing_last_changed_reason = f"PayPal subscription CANCELLED at {now}"
        
    elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
        # Suspend agency access
        access.status = "suspended"
        access.billing_mode = "paypal"
        access.paypal_status = "suspended"
        access.paypal_last_event_at = now
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_suspended"
        access.admin_alert_message = f"PayPal subscription SUSPENDED at {now}"
        access.billing_last_changed_reason = f"PayPal subscription SUSPENDED at {now}"
        
    elif event_type == "BILLING.SUBSCRIPTION.EXPIRED":
        # Suspend agency access
        access.status = "suspended"
        access.billing_mode = "paypal"
        access.paypal_status = "expired"
        access.paypal_last_event_at = now
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_expired"
        access.admin_alert_message = f"PayPal subscription EXPIRED at {now}"
        access.billing_last_changed_reason = f"PayPal subscription EXPIRED at {now}"
        
    elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        # Keep active but flag for admin attention
        access.paypal_status = "active"  # Still active until actually cancelled
        access.paypal_last_event_at = now
        access.needs_admin_attention = True
        access.admin_alert_code = "paypal_payment_failed"
        access.admin_alert_message = f"PayPal payment FAILED at {now}"
        access.billing_last_changed_reason = f"PayPal payment FAILED at {now}"
        
    elif event_type == "PAYMENT.SALE.COMPLETED":
        # Payment successful - ensure access is active
        if access.status == "suspended" and access.paypal_status == "active":
            # Reactivate if it was suspended due to payment issue
            access.status = "active"
            access.needs_admin_attention = False
            access.admin_alert_code = "none"
            access.admin_alert_message = ""
            access.billing_last_changed_reason = f"PayPal payment COMPLETED - reactivated at {now}"
            
            # Extend access period
            from datetime import timedelta
            access.access_ends_at = now + timedelta(days=30)
        
        access.paypal_last_event_at = now
    
    # Save the changes
    access.save(update_fields=[
        "status", "billing_mode", "paypal_status", "paypal_last_event_at",
        "paypal_cancelled_at", "needs_admin_attention", "admin_alert_code",
        "admin_alert_message", "billing_last_changed_reason", "access_ends_at"
    ])


def _create_alert_if_needed(access, event_type):
    """Create an AdminAlert for events that require superadmin attention."""
    alert_map = {
        "BILLING.SUBSCRIPTION.CANCELLED": (
            "paypal_cancelled",
            "L'agence {name} a annulé son abonnement PayPal. Basculé en mode manuel.",
        ),
        "BILLING.SUBSCRIPTION.PAYMENT.FAILED": (
            "paypal_failed",
            "Paiement PayPal échoué pour l'agence {name}. Vérifier le renouvellement.",
        ),
        "BILLING.SUBSCRIPTION.SUSPENDED": (
            "paypal_suspended",
            "Abonnement PayPal suspendu pour l'agence {name}.",
        ),
        "BILLING.SUBSCRIPTION.EXPIRED": (
            "paypal_expired",
            "Abonnement PayPal expiré pour l'agence {name}. Renouvellement manuel requis.",
        ),
    }

    if event_type not in alert_map:
        return

    alert_type, msg_template = alert_map[event_type]
    agency = access.agency
    AdminAlert.objects.create(
        alert_type=alert_type,
        agency=agency,
        message=msg_template.format(name=agency.name),
    )
