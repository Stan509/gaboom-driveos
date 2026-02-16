import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import AgencyAccess
from agencies.services import get_plan_config

# Mettre à jour les fonctionnalités pour toutes les agences business
business_accesses = AgencyAccess.objects.filter(plan_code='business')
print(f'📋 Mise à jour des fonctionnalités pour {business_accesses.count()} agences business...')

for access in business_accesses:
    plan_config = get_plan_config(access.plan_code)
    features = plan_config.get('features', {})
    
    print(f'\n🏢 {access.agency.name}')
    print(f'   Anciennes fonctionnalités: {access.plan_features}')
    
    # Mettre à jour avec les fonctionnalités du plan business
    access.plan_features = features
    access.save()
    
    print(f'   Nouvelles fonctionnalités: {access.plan_features}')
    print(f'   ✅ Portail client: {"Oui" if features.get("client_portal") else "Non"}')

print(f'\n✅ Fonctionnalités mises à jour ! Le portail client devrait maintenant être accessible.')
