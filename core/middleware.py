from django.http import Http404
from django.shortcuts import redirect

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
        if (
            request.user.is_authenticated
            and not request.user.email_verified
            and request.path_info.startswith("/dashboard/")
        ):
            return redirect("verify_required")

        return self.get_response(request)
