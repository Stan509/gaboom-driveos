import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import Agency

# Activer le portail client pour l'agence business
try:
    agency = Agency.objects.get(slug='agence-business')
    agency.client_portal_enabled = True
    agency.save()
    print(f'✅ Espace client activé pour {agency.name}')
    print(f'URL: http://localhost:8000/a/{agency.slug}/c/')
except Agency.DoesNotExist:
    print('❌ Agence business non trouvée')
except Exception as e:
    print(f'❌ Erreur: {e}')
