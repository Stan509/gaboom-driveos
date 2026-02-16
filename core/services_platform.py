"""
Central service to retrieve PayPal configuration.
Reads from PlatformSettings (DB) first, falls back to environment variables.
Uses per-mode (sandbox/live) fields.
"""

import logging
import os

logger = logging.getLogger(__name__)


def get_paypal_config() -> dict:
    """
    Return a dict with all PayPal configuration values.
    Priority: DB (PlatformSettings per-mode accessors) → environment variables.
    """
    from core.models_platform import PlatformSettings

    ps = PlatformSettings.get()

    mode = ps.paypal_mode or os.environ.get("PAYPAL_MODE", "sandbox")

    # Client ID (per-mode accessor falls back to legacy field)
    client_id = ps.active_client_id or os.environ.get("PAYPAL_CLIENT_ID", "")

    # Client Secret (per-mode accessor decrypts, falls back to legacy, then env)
    client_secret = ps.active_client_secret
    if not client_secret:
        client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "")

    # Plan ID
    plan_id = ps.active_plan_id
    if not plan_id:
        if mode == "live":
            plan_id = os.environ.get("PAYPAL_PLAN_ID_LIVE", "")
        else:
            plan_id = os.environ.get("PAYPAL_PLAN_ID_SANDBOX", "")

    # Product ID
    product_id = ps.active_product_id

    # Base URL
    base_url = ps.public_base_url or os.environ.get("PUBLIC_BASE_URL", "")

    # Webhook
    webhook_id = ps.active_webhook_id or os.environ.get("PAYPAL_WEBHOOK_ID", "")
    webhook_verify = ps.paypal_webhook_verify

    # API base URL
    api_base = ps.get_paypal_api_base()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "mode": mode,
        "plan_id": plan_id,
        "product_id": product_id,
        "base_url": base_url,
        "webhook_id": webhook_id,
        "webhook_verify": webhook_verify,
        "api_base": api_base,
        "webhook_url": f"{base_url.rstrip('/')}/webhooks/paypal/" if base_url else "",
        "enable_paypal_auto": ps.enable_paypal_auto,
        "price": str(ps.subscription_price),
        "currency": ps.subscription_currency,
    }
