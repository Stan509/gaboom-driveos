from __future__ import annotations

from dataclasses import dataclass

from django.template.loader import render_to_string


@dataclass(frozen=True)
class GeneratedPdf:
    filename: str
    content: bytes


def generate_contract_pdf(*, contract, agency, request) -> GeneratedPdf:
    """Render contract PDF using WeasyPrint.

    Note: WeasyPrint needs an absolute base_url so that MEDIA/STATIC URLs resolve.
    """
    from weasyprint import HTML

    # Choix du template selon la langue de l'agence
    lang = getattr(contract.agency, "language", "fr")
    template_map = {
        "es": "contracts/contract_es.html",
        "en": "contracts/contract_en.html",
        "ht": "contracts/contract_ht.html",
        "fr": "contracts/contract_fr.html",
    }
    template_name = template_map.get(lang, "contracts/contract_fr.html")

    html = render_to_string(
        template_name,
        {
            "contract": contract,
            "agency": agency,
            "client": contract.client,
            "vehicle": contract.vehicle,
        },
        request=request,
    )

    base_url = request.build_absolute_uri("/")
    pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()

    return GeneratedPdf(filename=f"contrat_{contract.pk}.pdf", content=pdf_bytes)
