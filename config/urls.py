from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404
from django.urls import include, path
from django.contrib.auth import views as auth_views

from agencies.paypal_webhooks import paypal_webhook
from core.views import resend_verification, test_notif_admin, verify_email, verify_required
from core.views_auth import RoleBasedLoginView
from core.views_health import health_check, readiness_check, liveness_check


# ── Superuser-only admin gate ──────────────────────────────────────────
# Even if the middleware is bypassed, this wrapper ensures /admin/ is
# never served to non-superusers.  In production (DEBUG=False) non-
# superuser requests get a 404 instead of a redirect.

def _superuser_admin_gate(view_func):
    """Wrap a view so only superusers can access it."""
    from functools import wraps

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            if settings.DEBUG:
                from django.shortcuts import redirect
                return redirect("/login/")
            raise Http404
        return view_func(request, *args, **kwargs)

    return _wrapped


admin.site.admin_view = lambda view, cacheable=False: _superuser_admin_gate(view)


def _offline(request):
    from django.shortcuts import render
    return render(request, "offline.html")


urlpatterns = [
    # Healthcheck endpoints (no authentication required)
    path("health/", health_check, name="health_check"),
    path("health/ready/", readiness_check, name="readiness_check"),
    path("health/live/", liveness_check, name="liveness_check"),
    
    # Application URLs
    path("offline/", _offline, name="offline"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("admin/", admin.site.urls),
    path("login/", RoleBasedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("verify-email/<uidb64>/<token>/", verify_email, name="verify_email"),
    path("verify-required/", verify_required, name="verify_required"),
    path("resend-verification/", resend_verification, name="resend_verification"),
    path("test-notif-admin/", test_notif_admin, name="test_notif_admin"),
    path("webhooks/paypal/", paypal_webhook, name="paypal_webhook"),
    path("billing/", include("billing.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("saas/", include("superadmin.urls")),
    path("a/", include("public_site.urls")),
    path("t/<str:token>/", __import__("dashboard.views_marketing", fromlist=["track_click"]).track_click, name="track_click"),
    path("", include("marketing.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
