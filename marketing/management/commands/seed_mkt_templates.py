"""
Management command to seed global premium marketing templates.
Usage: python manage.py seed_mkt_templates
"""
from django.core.management.base import BaseCommand

from marketing.models import MarketingTemplate


TEMPLATES = [
    # -- PROMO --
    {
        "key": "promo_email_simple",
        "name": "Promo - Email Simple",
        "objective": "promo",
        "style": "simple",
        "channel": "email",
        "subject": "Offre speciale chez {agence} !",
        "content": (
            "Bonjour {nom},\n\n"
            "Profitez de notre offre exclusive : {offre}\n\n"
            "Reservez des maintenant votre {voiture} a partir de {prix}.\n\n"
            ">> {lien}\n\n"
            "A tres bientot,\n"
            "L'equipe {agence}"
        ),
        "is_premium": True,
    },
    {
        "key": "promo_wa_simple",
        "name": "Promo - WhatsApp Simple",
        "objective": "promo",
        "style": "simple",
        "channel": "whatsapp",
        "subject": "",
        "content": (
            "Bonjour {nom}\n\n"
            "Offre speciale chez *{agence}* !\n"
            "{offre}\n\n"
            "Reservez votre {voiture} a {prix}\n"
            ">> {lien}"
        ),
        "is_premium": True,
    },
    {
        "key": "promo_email_luxe",
        "name": "Promo - Email Luxe",
        "objective": "promo",
        "style": "luxe",
        "channel": "email",
        "subject": "Experience Premium - {agence}",
        "content": (
            "Cher(e) {nom},\n\n"
            "Nous avons le plaisir de vous proposer une experience de conduite exceptionnelle.\n\n"
            "{offre}\n\n"
            "Decouvrez notre {voiture}, disponible des {prix}.\n"
            "Un vehicule d'exception pour des moments inoubliables.\n\n"
            "Reservez votre experience : {lien}\n\n"
            "Avec nos salutations distinguees,\n"
            "{agence} - {ville}"
        ),
        "is_premium": True,
    },
    # -- RELANCE --
    {
        "key": "relance_email_urgent",
        "name": "Relance - Email Urgent",
        "objective": "relance",
        "style": "urgent",
        "channel": "email",
        "subject": "Derniere chance - votre reservation expire !",
        "content": (
            "Bonjour {nom},\n\n"
            "ATTENTION : Votre reservation est en attente et expire bientot !\n\n"
            "Ne manquez pas votre {voiture} a {prix}.\n"
            "{offre}\n\n"
            "Confirmez maintenant : {lien}\n\n"
            "L'equipe {agence}"
        ),
        "is_premium": True,
    },
    {
        "key": "relance_wa_urgent",
        "name": "Relance - WhatsApp Urgent",
        "objective": "relance",
        "style": "urgent",
        "channel": "whatsapp",
        "subject": "",
        "content": (
            "{nom}, votre reservation expire bientot !\n\n"
            "Votre *{voiture}* a *{prix}* vous attend.\n"
            "{offre}\n\n"
            "Confirmez ici : {lien}"
        ),
        "is_premium": True,
    },
    # -- FIDELISATION --
    {
        "key": "fidelisation_email_corporate",
        "name": "Fidelisation - Email Corporate",
        "objective": "fidelisation",
        "style": "corporate",
        "channel": "email",
        "subject": "Merci pour votre fidelite, {nom} !",
        "content": (
            "Bonjour {nom},\n\n"
            "Merci de faire confiance a {agence} pour vos deplacements.\n\n"
            "En tant que client fidele, nous vous offrons : {offre}\n\n"
            "Decouvrez nos nouveaux vehicules et profitez de tarifs preferentiels.\n\n"
            ">> {lien}\n\n"
            "Cordialement,\n"
            "{agence} - {ville}"
        ),
        "is_premium": True,
    },
    {
        "key": "fidelisation_wa_simple",
        "name": "Fidelisation - WhatsApp Simple",
        "objective": "fidelisation",
        "style": "simple",
        "channel": "whatsapp",
        "subject": "",
        "content": (
            "Bonjour {nom}\n\n"
            "Merci pour votre fidelite chez *{agence}* !\n"
            "Voici une offre rien que pour vous : {offre}\n\n"
            ">> {lien}"
        ),
        "is_premium": True,
    },
    # -- AVIS --
    {
        "key": "avis_email_simple",
        "name": "Avis client - Email Simple",
        "objective": "avis",
        "style": "simple",
        "channel": "email",
        "subject": "Votre avis compte, {nom} !",
        "content": (
            "Bonjour {nom},\n\n"
            "Nous esperons que votre experience avec {agence} a ete agreable.\n\n"
            "Votre avis nous aide a nous ameliorer.\n"
            "Prenez 30 secondes pour nous noter :\n\n"
            ">> {lien}\n\n"
            "Merci,\n"
            "L'equipe {agence}"
        ),
        "is_premium": True,
    },
    # -- LANCEMENT --
    {
        "key": "lancement_email_ultra_premium",
        "name": "Lancement - Email Ultra Premium",
        "objective": "lancement",
        "style": "ultra_premium",
        "channel": "email",
        "subject": "Nouveau chez {agence} - Decouvrez en avant-premiere",
        "content": (
            "Cher(e) {nom},\n\n"
            "Nous sommes ravis de vous presenter en exclusivite :\n"
            "Le tout nouveau {voiture}.\n\n"
            "Une experience de conduite inedite, un design a couper le souffle.\n"
            "Disponible des maintenant a partir de {prix}.\n\n"
            "{offre}\n\n"
            "Reservez votre essai : {lien}\n\n"
            "Avec passion,\n"
            "{agence} - L'excellence automobile"
        ),
        "is_premium": True,
    },
    {
        "key": "lancement_wa_ultra_premium",
        "name": "Lancement - WhatsApp Ultra Premium",
        "objective": "lancement",
        "style": "ultra_premium",
        "channel": "whatsapp",
        "subject": "",
        "content": (
            "*Nouveau chez {agence}* !\n\n"
            "Decouvrez le *{voiture}* en avant-premiere.\n"
            "A partir de *{prix}*\n"
            "{offre}\n\n"
            ">> {lien}"
        ),
        "is_premium": True,
    },
]


class Command(BaseCommand):
    help = "Seed global premium marketing templates (agency=None)."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for tpl in TEMPLATES:
            obj, was_created = MarketingTemplate.objects.update_or_create(
                agency=None,
                key=tpl["key"],
                defaults={
                    "name": tpl["name"],
                    "objective": tpl["objective"],
                    "style": tpl["style"],
                    "channel": tpl["channel"],
                    "subject": tpl["subject"],
                    "content": tpl["content"],
                    "is_premium": tpl["is_premium"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created} created, {updated} updated ({len(TEMPLATES)} total templates)."
            )
        )
