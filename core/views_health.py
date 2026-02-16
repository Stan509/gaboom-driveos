"""
Healthcheck endpoint for production monitoring.
Fast, lightweight endpoint that returns HTTP 200 with service status.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
import time


@require_GET
def health_check(request):
    """
    Simple healthcheck endpoint.
    
    Returns HTTP 200 with JSON {"status": "ok", "timestamp": "..."}
    No database queries, very fast response.
    
    Used by:
    - Docker/Kubernetes health checks
    - Load balancers
    - Monitoring systems
    - Dokku healthchecks
    """
    # Very lightweight check - no database queries
    # Optional: check cache connectivity if available
    cache_healthy = True
    try:
        # Simple cache set/get to verify Redis/Memcached connectivity
        cache.set('health_check', 'ok', 10)
        cache.get('health_check')
    except Exception:
        cache_healthy = False
    
    response_data = {
        "status": "ok",
        "timestamp": timezone.now().isoformat(),
        "service": "gaboom-driveos",
        "version": getattr(settings, 'VERSION', 'unknown'),
        "cache_healthy": cache_healthy,
    }
    
    return JsonResponse(response_data, status=200)


@require_GET
def readiness_check(request):
    """
    Readiness probe - checks if the application is ready to serve traffic.
    Includes database connectivity check.
    """
    from django.db import connection
    
    # Check database connectivity
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_healthy = False
    
    # Check cache connectivity
    cache_healthy = True
    try:
        cache.set('readiness_check', 'ok', 10)
        cache.get('readiness_check')
    except Exception:
        cache_healthy = False
    
    all_healthy = db_healthy and cache_healthy
    status_code = 200 if all_healthy else 503
    
    response_data = {
        "status": "ready" if all_healthy else "not_ready",
        "timestamp": timezone.now().isoformat(),
        "checks": {
            "database": db_healthy,
            "cache": cache_healthy,
        }
    }
    
    return JsonResponse(response_data, status=status_code)


@require_GET
def liveness_check(request):
    """
    Liveness probe - checks if the application is still alive.
    Very lightweight, no external dependencies.
    """
    response_data = {
        "status": "alive",
        "timestamp": timezone.now().isoformat(),
        "uptime": time.time() - getattr(settings, 'START_TIME', time.time()),
    }
    
    return JsonResponse(response_data, status=200)
