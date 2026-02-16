import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import Agency, AgencyAccess
from agencies.services import get_plan_config

# Récupérer toutes les agences avec le plan business
business_plans = AgencyAccess.objects.filter(plan_code='business')
print(f'📋 Agences avec le plan business: {business_plans.count()}')

activated_count = 0
for access in business_plans:
    agency = access.agency
    if not agency.client_portal_enabled:
        agency.client_portal_enabled = True
        agency.save()
        print(f'✅ Espace client activé pour: {agency.name} ({agency.slug})')
        print(f'   URL: http://localhost:8000/a/{agency.slug}/c/')
        activated_count += 1
    else:
        print(f'ℹ️  Espace client déjà activé pour: {agency.name}')

print(f'\n🎉 Total activé: {activated_count} agence(s)')

# Vérifier les identifiants clients disponibles
from clients.models import ClientAccount
clients = ClientAccount.objects.filter(agency__in=[access.agency for access in business_plans])
print(f'\n👥 Comptes clients disponibles: {clients.count()}')
for client in clients[:3]:  # Limiter à 3 pour la lisibilité
    print(f'   - {client.email} (Agence: {client.agency.slug})')
