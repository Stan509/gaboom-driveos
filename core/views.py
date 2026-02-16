import time

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.mail import mail_admins, EmailMultiAlternatives, get_connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

User = get_user_model()


def _send_platform_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str = "",
    template_key: str = "",
    agency=None,
    max_attempts: int = 3,
    smtp_password_override: str = "",
    smtp_api_key_override: str = "",
    platform_settings=None,
) -> bool:
    from core.models_platform import PlatformSettings, EmailSendLog
    from core.models_admin_alert import AdminAlert
    ps = platform_settings or PlatformSettings.get()
    provider = ps.smtp_provider or "brevo_api"
    if provider == "smtp" and ps.smtp_host:
        smtp_password = smtp_password_override or ps.smtp_password
        connection = get_connection(
            "django.core.mail.backends.smtp.EmailBackend",
            host=ps.smtp_host,
            port=ps.smtp_port or 587,
            username=ps.smtp_username or "",
            password=smtp_password or "",
            use_tls=ps.smtp_use_tls,
            use_ssl=ps.smtp_use_ssl,
            timeout=10,
        )
    else:
        api_key = smtp_api_key_override or ps.smtp_api_key or settings.ANYMAIL.get("BREVO_API_KEY", "")
        if api_key:
            settings.ANYMAIL["BREVO_API_KEY"] = api_key
        if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            settings.EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
        connection = get_connection()
        provider = "brevo_api"
    from_email = ps.smtp_from_email or settings.DEFAULT_FROM_EMAIL
    reply_to = [ps.smtp_reply_to] if ps.smtp_reply_to else None
    log = EmailSendLog.objects.create(
        template_key=template_key or "",
        to_email=to_email,
        subject=subject,
        provider=provider,
        attempts=0,
        status="pending",
        agency=agency,
    )
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=body_text,
                from_email=from_email,
                to=[to_email],
                reply_to=reply_to,
                connection=connection,
            )
            if body_html:
                message.attach_alternative(body_html, "text/html")
            message.send(fail_silently=False)
            log.attempts = attempt
            log.status = "sent"
            log.last_error = ""
            log.save(update_fields=["attempts", "status", "last_error", "updated_at"])
            return True
        except Exception as exc:
            last_error = str(exc)
            log.attempts = attempt
            log.status = "failed"
            log.last_error = last_error
            log.save(update_fields=["attempts", "status", "last_error", "updated_at"])
    AdminAlert.objects.create(
        alert_type="email_failed",
        agency=agency,
        message=f"Echec envoi email {template_key or ''} vers {to_email}. {last_error}",
    )
    return False


def _send_verification_email(request: HttpRequest, user) -> None:
    from core.models_platform import EmailTemplate
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    link = f"{scheme}://{host}/verify-email/{uid}/{token}/"
    default_subject = "Gaboom DriveOS — Vérifie ton email"
    default_body = (
        f"Salut {user.username},\n\n"
        f"Clique sur ce lien pour activer ton compte :\n{link}\n\n"
        "Ce lien expire après quelques jours.\n\n"
        "— L'équipe Gaboom DriveOS"
    )
    template = EmailTemplate.objects.filter(key="verify_email", is_active=True).first()
    subject = default_subject
    body_text = default_body
    body_html = ""
    if template:
        data = {
            "username": user.username,
            "email": user.email,
            "link": link,
            "agency": getattr(user.agency, "name", ""),
        }
        try:
            subject = template.subject.format(**data)
            body_text = template.body_text.format(**data)
            body_html = template.body_html.format(**data) if template.body_html else ""
        except Exception:
            subject = default_subject
            body_text = default_body
            body_html = ""
    _send_platform_email(
        to_email=user.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        template_key="verify_email",
        agency=user.agency,
    )


def verify_email(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        agency = user.agency
        if agency and not agency.is_active:
            agency.is_active = True
            agency.save(update_fields=["is_active"])
        return render(request, "auth/verify_success.html", {"user": user})
    else:
        return render(request, "auth/verify_invalid.html", status=400)


@login_required
def verify_required(request: HttpRequest) -> HttpResponse:
    if request.user.email_verified:
        return redirect("dashboard:home")
    return render(request, "auth/verify_required.html", {"user": request.user})


@login_required
def resend_verification(request: HttpRequest) -> HttpResponse:
    if request.user.email_verified:
        return redirect("dashboard:home")

    if request.method != "POST":
        return redirect("verify_required")

    last_sent = request.session.get("_verify_last_sent", 0)
    now = time.time()
    if now - last_sent < 60:
        remaining = int(60 - (now - last_sent))
        return render(request, "auth/verify_required.html", {
            "user": request.user,
            "cooldown": remaining,
        })

    _send_verification_email(request, request.user)
    request.session["_verify_last_sent"] = now
    return render(request, "auth/verify_required.html", {
        "user": request.user,
        "resent": True,
    })


def test_notif_admin(request: HttpRequest) -> JsonResponse:
    """Vue de test — envoie un mail_admins() pour vérifier la config SMTP."""
    try:
        mail_admins(
            subject="Test notification admin depuis Django",
            message=(
                "Ceci est un email de test envoyé depuis Gaboom DriveOS.\n\n"
                "Si tu reçois ce message, la configuration SMTP Brevo fonctionne correctement.\n\n"
                f"Utilisateur connecté : {request.user}\n"
                f"Host : {request.get_host()}\n"
            ),
            fail_silently=False,
        )
        return JsonResponse({"status": "ok", "message": "Email envoyé aux ADMINS avec succès."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
