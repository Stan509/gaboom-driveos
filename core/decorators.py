from functools import wraps

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect


def _check_agency(request):
    """Return HttpResponseForbidden if user has no agency, else None."""
    if not getattr(request.user, "agency_id", None):
        return HttpResponseForbidden("Accès refusé : aucune agence associée.")
    return None


def require_agency_user(view_func):
    """Ensure the user is logged in AND has an agency attached.
    Any role (owner, admin, staff) is accepted."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        err = _check_agency(request)
        if err:
            return err
        return view_func(request, *args, **kwargs)

    return _wrapped


def require_agency_admin(view_func):
    """Ensure the user is logged in, has an agency, and role is owner or manager.
    Use for: CRUD véhicules, clients."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        err = _check_agency(request)
        if err:
            return err
        if request.user.role not in ("agency_owner", "agency_manager"):
            return HttpResponseForbidden("Accès refusé : droits insuffisants.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def require_agency_owner(view_func):
    """Ensure the user is logged in, has an agency, and role is owner.
    Use for: paramètres agence, billing, Stripe."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        err = _check_agency(request)
        if err:
            return err
        if request.user.role != "agency_owner":
            return HttpResponseForbidden("Accès refusé : réservé au propriétaire de l'agence.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def require_superadmin(view_func):
    """Only superusers can access. In DEBUG → redirect /login/. In prod → 404."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            if django_settings.DEBUG:
                return redirect("/login/")
            raise Http404
        return view_func(request, *args, **kwargs)

    return _wrapped
