from functools import wraps

from django.shortcuts import redirect

from clients.models import ClientAccount


SESSION_KEY = "client_account_id"
SESSION_AGENCY = "client_agency_slug"


def get_client_from_session(request, slug):
    """Return ClientAccount if session is valid for this agency slug, else None."""
    cid = request.session.get(SESSION_KEY)
    cslug = request.session.get(SESSION_AGENCY)
    if not cid or cslug != slug:
        return None
    try:
        return ClientAccount.objects.select_related("agency").get(
            pk=cid, agency__slug=slug, is_active=True,
        )
    except ClientAccount.DoesNotExist:
        return None


def require_client_login(view_func):
    """Decorator for client portal views under /a/<slug>/c/...
    Expects `slug` as a keyword argument from the URL pattern."""

    @wraps(view_func)
    def _wrapped(request, slug, *args, **kwargs):
        client = get_client_from_session(request, slug)
        if not client:
            return redirect("public_site:client_login", slug=slug)
        request.client_account = client
        return view_func(request, slug, *args, **kwargs)

    return _wrapped
