from django.contrib import messages
from django.shortcuts import redirect

from agencies.services import get_agency_access, sync_access

# Paths that are always allowed even when suspended
ALLOWED_PATHS = (
    "/dashboard/subscription",
    "/dashboard/abonnement",
    "/logout/",
    "/login/",
    "/admin/",
    "/verify-required/",
    "/verify-email/",
    "/resend-verification/",
    "/static/",
    "/media/",
)


class RequireActiveAccessMiddleware:
    """Block all dashboard access for suspended agencies (except subscription page)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Superusers are never blocked
        if request.user.is_superuser:
            return self.get_response(request)

        # Only block dashboard paths
        if not request.path_info.startswith("/dashboard/"):
            return self.get_response(request)

        # Check allowed paths
        for path in ALLOWED_PATHS:
            if request.path_info.startswith(path):
                return self.get_response(request)

        # User must have an agency
        agency = getattr(request.user, "agency", None)
        if not agency:
            return self.get_response(request)

        # Get or create access, sync status
        access = get_agency_access(agency)
        sync_access(access)

        # PayPal active: never block even if access_ends_at is close
        if access.billing_mode == "paypal" and access.paypal_status == "active":
            return self.get_response(request)

        if access.status == "suspended" or access.should_block_now:
            messages.warning(
                request,
                "Compte suspendu — renouvellement requis. "
                "Rendez-vous sur la page Abonnement pour plus d'informations.",
            )
            return redirect("dashboard:subscription")

        return self.get_response(request)
