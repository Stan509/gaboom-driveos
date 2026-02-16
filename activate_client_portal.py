import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import Agency

# Récupérer l'agence business
agency = Agency.objects.filter(slug='agence-business').first()

if agency:
    print(f'Agence: {agency.name}')
    print(f'Slug: {agency.slug}')
    print(f'Client portal enabled: {agency.client_portal_enabled}')
    
    # Activer le portail client
    agency.client_portal_enabled = True
    agency.save()
    
    print(f'✅ Client portal activé pour {agency.name}')
    print(f'URL du portail client: http://localhost:8000/a/{agency.slug}/c/')
else:
    print('❌ Agence "agence-business" non trouvée')
    
# Afficher toutes les agences avec leur statut
print('\n📋 Liste des agences:')
for a in Agency.objects.all():
    print(f'  - {a.name} ({a.slug}): {"✅ Activé" if a.client_portal_enabled else "❌ Désactivé"}')
