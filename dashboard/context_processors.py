from billing.models import Contract

def global_dashboard_data(request):
    """
    Global data for dashboard layout.
    Provides unsigned_contracts_count for sidebar badge.
    """
    if not request.user.is_authenticated:
        return {"unsigned_contracts_count": 0}
    try:
        # Use the agency-scoped manager if available
        agency = getattr(request.user, "agency", None)
        if agency:
            count = Contract.objects.for_agency(agency).exclude(status="signed").count()
        else:
            count = Contract.objects.exclude(status="signed").count()
    except Exception:
        count = 0
    return {"unsigned_contracts_count": count}
