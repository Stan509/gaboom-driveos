"""
PayPal REST API helpers.
All functions read config via get_paypal_config().
Supports: OAuth, plan CRUD, subscription creation, webhook signature verification.
"""

import logging

import requests as http_requests

from core.services_platform import get_paypal_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Low-level helpers
# ═══════════════════════════════════════════════════════════════════════

def _api_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def paypal_get_access_token(cfg: dict | None = None) -> str | None:
    """Get a fresh PayPal OAuth2 access token. Returns token string or None."""
    if cfg is None:
        cfg = get_paypal_config()
    if not cfg["client_id"] or not cfg["client_secret"]:
        return None
    url = f"{cfg['api_base']}/v1/oauth2/token"
    try:
        resp = http_requests.post(
            url,
            data={"grant_type": "client_credentials"},
            auth=(cfg["client_id"], cfg["client_secret"]),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token", "")
    except http_requests.RequestException:
        logger.exception("PayPal OAuth token request failed")
    return None


def paypal_api_request(method: str, path: str, json_data: dict | None = None,
                       cfg: dict | None = None) -> dict:
    """
    Generic PayPal API request.
    Returns {"ok": bool, "status": int, "data": dict, "message": str}.
    """
    if cfg is None:
        cfg = get_paypal_config()
    token = paypal_get_access_token(cfg)
    if not token:
        return {"ok": False, "status": 0, "data": {}, "message": "Impossible d'obtenir un token PayPal."}

    url = f"{cfg['api_base']}{path}"
    try:
        resp = http_requests.request(
            method, url, json=json_data, headers=_api_headers(token), timeout=20,
        )
    except http_requests.RequestException as exc:
        return {"ok": False, "status": 0, "data": {}, "message": f"Erreur réseau: {exc}"}

    ok = resp.status_code in (200, 201, 204)
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    return {
        "ok": ok,
        "status": resp.status_code,
        "data": data,
        "message": "" if ok else f"PayPal {resp.status_code}: {resp.text[:300]}",
    }


# ═══════════════════════════════════════════════════════════════════════
# OAuth Token Test
# ═══════════════════════════════════════════════════════════════════════

def test_oauth_token() -> dict:
    """
    Attempt to obtain a PayPal OAuth2 access token.
    Returns {"ok": bool, "message": str, "token": str|None}.
    """
    cfg = get_paypal_config()
    if not cfg["client_id"] or not cfg["client_secret"]:
        return {"ok": False, "message": "Client ID ou Secret manquant.", "token": None}

    token = paypal_get_access_token(cfg)
    if token:
        # Update last test status
        try:
            from django.utils import timezone
            from core.models_platform import PlatformSettings
            ps = PlatformSettings.get()
            ps.last_api_test_at = timezone.now()
            ps.last_api_test_ok = True
            ps.save(update_fields=["last_api_test_at", "last_api_test_ok", "updated_at"])
        except Exception:
            pass
        return {"ok": True, "message": f"Connexion OK (mode {cfg['mode']})", "token": token}

    try:
        from django.utils import timezone
        from core.models_platform import PlatformSettings
        ps = PlatformSettings.get()
        ps.last_api_test_at = timezone.now()
        ps.last_api_test_ok = False
        ps.save(update_fields=["last_api_test_at", "last_api_test_ok", "updated_at"])
    except Exception:
        pass
    return {"ok": False, "message": "Échec d'authentification PayPal. Vérifiez vos identifiants.", "token": None}


def _get_access_token() -> str | None:
    """Internal helper: get a fresh access token or None."""
    return paypal_get_access_token()


# ═══════════════════════════════════════════════════════════════════════
# Plan Validation
# ═══════════════════════════════════════════════════════════════════════

def test_plan(plan_id: str = "") -> dict:
    """
    Validate a PayPal billing plan by ID.
    Returns {"ok": bool, "message": str, "plan": dict|None}.
    """
    cfg = get_paypal_config()
    pid = plan_id or cfg["plan_id"]
    if not pid:
        return {"ok": False, "message": "Aucun Plan ID renseigné.", "plan": None}

    result = paypal_api_request("GET", f"/v1/billing/plans/{pid}", cfg=cfg)
    if result["ok"]:
        plan = result["data"]
        name = plan.get("name", "")
        status = plan.get("status", "")
        return {"ok": True, "message": f"Plan valide: \"{name}\" (status: {status})", "plan": plan}

    return {"ok": False, "message": result["message"], "plan": None}


# ═══════════════════════════════════════════════════════════════════════
# Product & Plan Creation
# ═══════════════════════════════════════════════════════════════════════

def create_or_get_product(cfg: dict | None = None,
                          name: str = "Gaboom DriveOS") -> dict:
    """
    Create a PayPal catalog product or reuse existing product_id from settings.
    Returns {"ok": bool, "product_id": str, "message": str}.
    """
    if cfg is None:
        cfg = get_paypal_config()

    # Reuse existing product_id if available
    existing = cfg.get("product_id", "")
    if existing:
        return {"ok": True, "product_id": existing, "message": f"Product existant: {existing}"}

    result = paypal_api_request("POST", "/v1/catalogs/products", {
        "name": name,
        "description": "Abonnement mensuel Gaboom DriveOS",
        "type": "SERVICE",
        "category": "SOFTWARE",
    }, cfg=cfg)

    if result["ok"]:
        pid = result["data"].get("id", "")
        return {"ok": True, "product_id": pid, "message": f"Product créé: {pid}"}
    return {"ok": False, "product_id": "", "message": result["message"]}


def create_plan(price: str = "", currency: str = "",
                name: str = "Gaboom DriveOS Mensuel",
                cfg: dict | None = None) -> dict:
    """
    Create a PayPal product (if needed) + billing plan.
    Returns {"ok": bool, "message": str, "plan_id": str|None, "product_id": str|None}.
    """
    if cfg is None:
        cfg = get_paypal_config()
    price = price or cfg.get("price", "29.99")
    currency = currency or cfg.get("currency", "USD")

    # 1) Product
    prod = create_or_get_product(cfg, name)
    if not prod["ok"]:
        return {"ok": False, "message": prod["message"], "plan_id": None, "product_id": None}
    product_id = prod["product_id"]

    # 2) Plan
    result = paypal_api_request("POST", "/v1/billing/plans", {
        "product_id": product_id,
        "name": f"{name} — Mensuel",
        "description": f"Abonnement mensuel {price} {currency}",
        "billing_cycles": [{
            "frequency": {"interval_unit": "MONTH", "interval_count": 1},
            "tenure_type": "REGULAR",
            "sequence": 1,
            "total_cycles": 0,
            "pricing_scheme": {
                "fixed_price": {"value": price, "currency_code": currency},
            },
        }],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "payment_failure_threshold": 3,
        },
    }, cfg=cfg)

    if result["ok"]:
        plan_id = result["data"].get("id", "")
        return {
            "ok": True,
            "message": f"Plan créé: {plan_id} (product: {product_id})",
            "plan_id": plan_id,
            "product_id": product_id,
        }
    return {"ok": False, "message": result["message"], "plan_id": None, "product_id": None}


# ═══════════════════════════════════════════════════════════════════════
# Subscription Creation (agency checkout)
# ═══════════════════════════════════════════════════════════════════════

def create_subscription(return_url: str, cancel_url: str,
                        custom_id: str = "",
                        cfg: dict | None = None) -> dict:
    """
    Create a PayPal subscription and return the approval URL.
    Returns {"ok": bool, "subscription_id": str, "approve_url": str, "message": str}.
    """
    if cfg is None:
        cfg = get_paypal_config()

    plan_id = cfg.get("plan_id", "")
    if not plan_id:
        return {"ok": False, "subscription_id": "", "approve_url": "",
                "message": "Aucun Plan ID configuré."}

    payload = {
        "plan_id": plan_id,
        "application_context": {
            "brand_name": "Gaboom DriveOS",
            "locale": "fr-FR",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    if custom_id:
        payload["custom_id"] = custom_id

    result = paypal_api_request("POST", "/v1/billing/subscriptions", payload, cfg=cfg)
    if not result["ok"]:
        return {"ok": False, "subscription_id": "", "approve_url": "",
                "message": result["message"]}

    data = result["data"]
    sub_id = data.get("id", "")
    approve_url = ""
    for link in data.get("links", []):
        if link.get("rel") == "approve":
            approve_url = link.get("href", "")
            break

    if not approve_url:
        return {"ok": False, "subscription_id": sub_id, "approve_url": "",
                "message": "Pas d'URL d'approbation retournée par PayPal."}

    return {"ok": True, "subscription_id": sub_id, "approve_url": approve_url, "message": "OK"}


def create_paypal_subscription(plan_id: str, return_url: str, cancel_url: str,
                             custom_id: str = "", cfg: dict | None = None) -> dict:
    """
    Create a PayPal subscription with a specific plan_id and return the approval URL.
    Returns {"subscription_id": str, "approval_url": str} or raises Exception.
    """
    if cfg is None:
        cfg = get_paypal_config()

    payload = {
        "plan_id": plan_id,
        "application_context": {
            "brand_name": "Gaboom DriveOS",
            "locale": "fr-FR",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    if custom_id:
        payload["custom_id"] = custom_id

    result = paypal_api_request("POST", "/v1/billing/subscriptions", payload, cfg=cfg)
    if not result["ok"]:
        raise Exception(f"PayPal API error: {result['message']}")

    data = result["data"]
    sub_id = data.get("id", "")
    approve_url = ""
    for link in data.get("links", []):
        if link.get("rel") == "approve":
            approve_url = link.get("href", "")
            break

    if not approve_url:
        raise Exception("PayPal did not return approval URL")

    return {
        "subscription_id": sub_id,
        "approval_url": approve_url,
        "product_id": data.get("product_id", ""),
    }


def get_subscription_details(subscription_id: str, cfg: dict | None = None) -> dict:
    """Fetch subscription details from PayPal."""
    result = paypal_api_request("GET", f"/v1/billing/subscriptions/{subscription_id}", cfg=cfg)
    if result["ok"]:
        return {"ok": True, "data": result["data"], "message": "OK"}
    return {"ok": False, "data": {}, "message": result["message"]}


# ═══════════════════════════════════════════════════════════════════════
# Webhook Signature Verification
# ═══════════════════════════════════════════════════════════════════════

def verify_webhook_signature(headers: dict, body: bytes, cfg: dict | None = None) -> bool:
    """
    Verify PayPal webhook signature using the Notifications API.
    Returns True if verified, False otherwise.
    """
    if cfg is None:
        cfg = get_paypal_config()

    webhook_id = cfg.get("webhook_id", "")
    if not webhook_id:
        logger.warning("Webhook signature verification skipped: no webhook_id configured")
        return False

    token = paypal_get_access_token(cfg)
    if not token:
        logger.error("Cannot verify webhook: failed to get access token")
        return False

    import json
    try:
        event_body = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return False

    verify_payload = {
        "auth_algo": headers.get("PAYPAL-AUTH-ALGO", ""),
        "cert_url": headers.get("PAYPAL-CERT-URL", ""),
        "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID", ""),
        "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG", ""),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME", ""),
        "webhook_id": webhook_id,
        "webhook_event": event_body,
    }

    url = f"{cfg['api_base']}/v1/notifications/verify-webhook-signature"
    try:
        resp = http_requests.post(
            url, json=verify_payload, headers=_api_headers(token), timeout=15,
        )
        if resp.status_code == 200:
            status = resp.json().get("verification_status", "")
            return status == "SUCCESS"
    except http_requests.RequestException:
        logger.exception("Webhook signature verification request failed")

    return False
