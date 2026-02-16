from django.db.models.signals import post_save
from django.dispatch import receiver


DEFAULT_PAGES = [
    {
        "title": "À propos",
        "slug": "a-propos",
        "template_variant": "about",
        "show_in_nav": True,
        "nav_order": 20,
        "is_published": True,
        "content": (
            "## Qui sommes-nous ?\n\n"
            "Bienvenue chez **{{ agency }}**. Nous sommes spécialisés dans la location de véhicules "
            "de qualité, avec un service client irréprochable.\n\n"
            "## Notre mission\n\n"
            "Offrir à nos clients des véhicules fiables, bien entretenus et à des tarifs compétitifs.\n\n"
            "## Pourquoi nous choisir ?\n\n"
            "- Véhicules récents et bien entretenus\n"
            "- Tarifs transparents, sans frais cachés\n"
            "- Service client réactif 7j/7\n"
            "- Réservation en ligne simple et rapide\n"
        ),
    },
    {
        "title": "FAQ",
        "slug": "faq",
        "template_variant": "faq",
        "show_in_nav": True,
        "nav_order": 30,
        "is_published": True,
        "content": (
            "## Comment réserver un véhicule ?\n\n"
            "Parcourez notre catalogue, choisissez un véhicule et remplissez le formulaire de réservation. "
            "Vous recevrez une confirmation par email.\n\n"
            "## Quels documents sont nécessaires ?\n\n"
            "Un permis de conduire valide et une pièce d'identité sont requis lors de la prise en charge.\n\n"
            "## Puis-je annuler ma réservation ?\n\n"
            "Oui, vous pouvez annuler gratuitement jusqu'à 24h avant la date de prise en charge.\n\n"
            "## Comment fonctionne le paiement ?\n\n"
            "Le paiement s'effectue lors de la prise en charge du véhicule. Nous acceptons les espèces et le virement.\n\n"
            "## Que faire en cas de panne ?\n\n"
            "Contactez-nous immédiatement. Nous vous fournirons un véhicule de remplacement dans les plus brefs délais.\n"
        ),
    },
    {
        "title": "Contact",
        "slug": "contact",
        "template_variant": "contact",
        "show_in_nav": True,
        "nav_order": 40,
        "is_published": True,
        "content": (
            "N'hésitez pas à nous contacter pour toute question ou demande de renseignement.\n\n"
            "Notre équipe est disponible du lundi au samedi, de 8h à 19h.\n"
        ),
    },
    {
        "title": "Conditions générales de location",
        "slug": "conditions",
        "template_variant": "legal",
        "show_in_nav": False,
        "nav_order": 100,
        "is_published": True,
        "content": (
            "## Article 1 – Objet\n\n"
            "Les présentes conditions générales régissent la location de véhicules proposée par l'agence.\n\n"
            "## Article 2 – Réservation\n\n"
            "Toute réservation est soumise à la disponibilité du véhicule et à la validation par l'agence.\n\n"
            "## Article 3 – Durée de location\n\n"
            "La durée minimale de location est de 24 heures. Toute journée entamée est due.\n\n"
            "## Article 4 – Responsabilité du locataire\n\n"
            "Le locataire est responsable du véhicule pendant toute la durée de la location.\n"
        ),
    },
    {
        "title": "Politique de confidentialité",
        "slug": "confidentialite",
        "template_variant": "legal",
        "show_in_nav": False,
        "nav_order": 101,
        "is_published": True,
        "content": (
            "## Collecte des données\n\n"
            "Nous collectons uniquement les données nécessaires à la gestion de votre réservation : "
            "nom, email, téléphone.\n\n"
            "## Utilisation\n\n"
            "Vos données sont utilisées exclusivement pour le traitement de vos réservations et la communication liée.\n\n"
            "## Conservation\n\n"
            "Vos données sont conservées pendant la durée nécessaire au traitement de votre dossier.\n\n"
            "## Vos droits\n\n"
            "Vous disposez d'un droit d'accès, de rectification et de suppression de vos données personnelles.\n"
        ),
    },
    {
        "title": "Mentions légales",
        "slug": "mentions-legales",
        "template_variant": "legal",
        "show_in_nav": False,
        "nav_order": 102,
        "is_published": True,
        "content": (
            "## Éditeur du site\n\n"
            "Ce site est édité par l'agence. Pour toute question, veuillez nous contacter via la page Contact.\n\n"
            "## Hébergement\n\n"
            "Ce site est hébergé par Gaboom DriveOS.\n\n"
            "## Propriété intellectuelle\n\n"
            "L'ensemble du contenu de ce site est protégé par le droit d'auteur.\n"
        ),
    },
]


@receiver(post_save, sender="agencies.Agency")
def create_agency_defaults(sender, instance, created, **kwargs):
    """Auto-create ThemeSettings + BusinessSettings when a new Agency is created."""
    if not created:
        return
    from agencies.models import AgencyThemeSettings, BusinessSettings
    AgencyThemeSettings.objects.get_or_create(agency=instance)
    BusinessSettings.objects.get_or_create(agency=instance)


@receiver(post_save, sender="agencies.Agency")
def create_default_pages(sender, instance, created, **kwargs):
    """Auto-create default CMS pages when a new Agency is created."""
    if not created:
        return

    from public_site.models import PublicPage

    existing_slugs = set(
        PublicPage.objects.filter(agency=instance).values_list("slug", flat=True)
    )

    for page_data in DEFAULT_PAGES:
        if page_data["slug"] in existing_slugs:
            continue
        content = page_data["content"].replace("{{ agency }}", instance.name)
        PublicPage.objects.create(
            agency=instance,
            title=page_data["title"],
            slug=page_data["slug"],
            template_variant=page_data["template_variant"],
            show_in_nav=page_data["show_in_nav"],
            nav_order=page_data["nav_order"],
            is_published=page_data["is_published"],
            content=content,
        )
