from __future__ import annotations

import base64
from datetime import datetime

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import translation

from core.permissions import require_perm
from billing.models import Contract

from .utils import generate_contract_pdf


def _agency(request: HttpRequest):
    return request.user.agency


@require_perm("contracts.view")
def contract_pdf_view(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    
    contract = get_object_or_404(
        Contract.objects.for_agency(agency).select_related(
            "client",
            "vehicle",
            "agency",
        ),
        pk=pk,
    )

    # Langue basée sur l'agence (robuste, pas de dépendance à ?lang)
    lang = getattr(contract.agency, "language", "fr")
    translation.activate(lang)

    pdf = generate_contract_pdf(contract=contract, agency=agency, request=request)

    response = HttpResponse(pdf.content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{pdf.filename}"'
    return response


@require_perm("contracts.edit")
def contract_sign_view(request: HttpRequest, pk: int) -> JsonResponse:
    """Receive base64 signature image and save to contract.client_signature."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    agency = _agency(request)
    contract = get_object_or_404(
        Contract.objects.for_agency(agency).select_related("client", "vehicle", "agency"),
        pk=pk,
    )

    data = request.POST.get("signature")
    if not data:
        return JsonResponse({"error": "signature data missing"}, status=400)

    # Remove data:image/png;base64, prefix if present
    if "," in data:
        data = data.split(",", 1)[1]

    try:
        # Decode base64
        image_data = base64.b64decode(data)
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contract_{contract.pk}_signature_{timestamp}.png"
        # Save to ImageField
        contract.client_signature.save(filename, content=image_data, save=True)
        contract.client_signed_at = datetime.now()
        contract.client_signed_ip = request.META.get("REMOTE_ADDR")
        contract.save(update_fields=["client_signature", "client_signed_at", "client_signed_ip"])
        return JsonResponse({"success": True, "filename": filename})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
