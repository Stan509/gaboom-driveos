from django.http import Http404
from django.shortcuts import redirect
import os

from agencies.models import Agency


class SuperAdminOnlyMiddleware:
    """Block /admin/ access for anyone who is not a superuser."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith("/admin/"):
            if not request.user.is_authenticated or not request.user.is_superuser:
                return redirect("/login/")
        return self.get_response(request)


class AgencyMiddleware:
    """Detecte une agence via `/a/<slug>/` et l'attache à la requête."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.agency = None
        path = request.path_info.strip("/")
        parts = path.split("/") if path else []

        if len(parts) >= 2 and parts[0] == "a":
            slug = parts[1]
            agency = Agency.objects.filter(slug=slug).first()
            if not agency or not agency.public_enabled:
                raise Http404("Agence introuvable")
            request.agency = agency
        return self.get_response(request)


class EmailVerificationMiddleware:
    """Redirect unverified users to verify_required page on /dashboard/* routes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        verification_required = (os.environ.get("EMAIL_VERIFICATION_REQUIRED", "1") or "1").strip().lower() in {
            "1", "true", "yes", "y", "on"
        }
        fail_open = (os.environ.get("EMAIL_FAIL_OPEN", "1") or "1").strip().lower() in {"1", "true", "yes", "y", "on"}

        if not verification_required:
            return self.get_response(request)

        if (
            request.user.is_authenticated
            and not request.user.email_verified
            and request.path_info.startswith("/dashboard/")
        ):
            if fail_open and request.session.get("_email_fail_open", False):
                return self.get_response(request)
            return redirect("verify_required")

        return self.get_response(request)
