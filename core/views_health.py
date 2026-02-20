"""
Healthcheck endpoint for production monitoring.
Fast, lightweight endpoint that returns HTTP 200 with service status.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    """
    Simple healthcheck endpoint.
    
    Returns HTTP 200 with JSON {"status": "ok"}
    No database queries, very fast response.
    
    Used by:
    - Docker/Kubernetes health checks
    - Load balancers
    - Monitoring systems
    - Dokku healthchecks
    """
    response_data = {
        "status": "ok"
    }

    if (request.GET.get("brevo") or "").strip() in {"1", "true", "yes", "on"}:
        from core.email import brevo_health
        response_data["brevo"] = brevo_health()
    
    return JsonResponse(response_data, status=200)
