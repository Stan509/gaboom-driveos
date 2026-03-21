import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['DJANGO_DEBUG'] = '1'
django.setup()

from django.utils import translation

# Test des traductions Campaigns
with translation.override('es'):
    test_strings = [
        'Campagnes IA',
        'Marketing Engine 2.0 — Créez, testez et optimisez vos campagnes',
        'Nouvelle campagne',
        'Envois total',
        'Clés API marketing',
        'Email',
        'configurée',
        'manquante',
        'WhatsApp',
        'Enregistrer',
        'Email expéditeur',
        'Clé API Email',
        'WhatsApp Phone ID',
        'Clé API WhatsApp',
        'Campagne',
        'Objectif',
        'Canaux',
        'Statut',
        'Envois',
        'Conv.',
        'A/B',
        'Actions',
        'Modifier',
        'Envoyer cette campagne ?',
        'Envoyer',
        'Supprimer ?',
        'Aucune campagne pour le moment',
        'Créez votre première campagne avec l\'assistant IA',
        'Créer une campagne'
    ]
    
    print('Test des traductions Campaigns (espagnol):')
    for s in test_strings:
        translated = translation.gettext(s)
        status = '✅' if translated != s else '❌'
        print(f'{status} "{s}" → "{translated}"')
