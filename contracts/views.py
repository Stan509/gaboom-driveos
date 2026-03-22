from __future__ import annotations

from django.http import HttpRequest, HttpResponse
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
    
    # Gestion de la langue pour le PDF
    lang = request.GET.get("lang") or request.LANGUAGE_CODE
    translation.activate(lang)
    
    contract = get_object_or_404(
        Contract.objects.for_agency(agency).select_related(
            "client",
            "vehicle",
            "agency",
        ),
        pk=pk,
    )

    pdf = generate_contract_pdf(contract=contract, agency=agency, request=request)

    response = HttpResponse(pdf.content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{pdf.filename}"'
    return response
