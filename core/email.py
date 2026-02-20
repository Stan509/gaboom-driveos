import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: str) -> bool:
    raw = os.environ.get(name, default)
    raw = (raw or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def get_brevo_api_key() -> str:
    key = os.environ.get("BREVO_API_KEY")
    if key is None:
        return ""
    key = key.strip()
    if len(key) >= 2 and ((key[0] == '"' and key[-1] == '"') or (key[0] == "'" and key[-1] == "'")):
        key = key[1:-1].strip()
    return key


def brevo_key_prefix(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    return key[:8]


@dataclass(frozen=True)
class BrevoConfig:
    api_key: str
    app_name: str
    default_from_email: str
    email_fail_open: bool
    email_verification_required: bool


def get_email_config() -> BrevoConfig:
    api_key = get_brevo_api_key()
    app_name = getattr(settings, "APP_NAME", None) or os.environ.get("APP_NAME", "Gaboom DriveOS")
    default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or os.environ.get(
        "DEFAULT_FROM_EMAIL", "no-reply@gaboomholding.com"
    )
    email_fail_open = _env_flag("EMAIL_FAIL_OPEN", "1")
    email_verification_required = _env_flag("EMAIL_VERIFICATION_REQUIRED", "1")
    return BrevoConfig(
        api_key=api_key,
        app_name=app_name,
        default_from_email=default_from_email,
        email_fail_open=email_fail_open,
        email_verification_required=email_verification_required,
    )


class BrevoError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


def brevo_headers(api_key: str) -> dict[str, str]:
    return {
        "api-key": api_key,
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def brevo_send_email(*, to_email: str, subject: str, html_content: str, sender_name: str, sender_email: str) -> dict[str, Any]:
    cfg = get_email_config()
    api_key = cfg.api_key
    if not api_key:
        raise BrevoError("BREVO_API_KEY missing")

    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }

    try:
        resp = requests.post(url, headers=brevo_headers(api_key), json=payload, timeout=10)
    except requests.RequestException as exc:
        raise BrevoError(f"Brevo request error: {exc}") from exc

    if resp.status_code >= 200 and resp.status_code < 300:
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        return {"ok": True, "status_code": resp.status_code, "data": data}

    text = (resp.text or "").strip()
    msg = f"Brevo API response {resp.status_code}: {text[:500]}"
    raise BrevoError(msg, status_code=resp.status_code, response_text=text)


def brevo_health() -> dict[str, Any]:
    cfg = get_email_config()
    api_key = cfg.api_key
    if not api_key:
        return {"ok": False, "status_code": None, "message": "BREVO_API_KEY missing"}

    try:
        resp = requests.get(
            "https://api.brevo.com/v3/account",
            headers={"api-key": api_key, "accept": "application/json"},
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"ok": False, "status_code": None, "message": str(exc)}

    if resp.status_code == 200:
        return {"ok": True, "status_code": 200, "message": "ok"}

    msg = (resp.text or "").strip()
    return {"ok": False, "status_code": resp.status_code, "message": msg[:500]}


def send_email(*, to_email: str, subject: str, html_content: str, sender_name: Optional[str] = None, sender_email: Optional[str] = None) -> dict[str, Any]:
    cfg = get_email_config()
    sender_name = sender_name or cfg.app_name
    sender_email = sender_email or cfg.default_from_email

    key_prefix = brevo_key_prefix(cfg.api_key)

    if not cfg.api_key:
        if settings.DEBUG:
            logger.warning("Email skipped (no BREVO_API_KEY)")
            return {"ok": True, "skipped": True, "reason": "missing_api_key"}
        if cfg.email_fail_open:
            logger.error("Email provider unavailable (no BREVO_API_KEY), fail-open enabled")
            return {"ok": False, "skipped": True, "reason": "missing_api_key"}
        return {"ok": False, "skipped": False, "reason": "missing_api_key"}

    try:
        result = brevo_send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            sender_email=sender_email,
        )
        return {"ok": True, "skipped": False, "provider": "brevo", **result}
    except BrevoError as exc:
        status = exc.status_code
        if status in (401, 403):
            logger.error(
                "Brevo unauthorized (%s) key_prefix=%s message=%s",
                status,
                key_prefix,
                str(exc)[:500],
            )
        else:
            logger.error(
                "Brevo send failed status=%s key_prefix=%s message=%s",
                status,
                key_prefix,
                str(exc)[:500],
            )

        if cfg.email_fail_open:
            return {"ok": False, "skipped": True, "reason": "brevo_failed", "status_code": status, "message": str(exc)}
        return {"ok": False, "skipped": False, "reason": "brevo_failed", "status_code": status, "message": str(exc)}
