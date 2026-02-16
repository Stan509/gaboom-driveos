import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import Agency, AgencyAccess
from agencies.services import get_agency_access, get_plan_config

# Tester pour l'agence agence-business
agency = Agency.objects.get(slug='agence-business')
print(f'🏢 Agence: {agency.name} ({agency.slug})')

access = get_agency_access(agency)
print(f'📋 Access trouvé: {access}')
print(f'   Plan code: {access.plan_code}')
print(f'   Plan name: {access.plan_name}')
print(f'   Plan features: {access.plan_features}')

# Vérifier la fonctionnalité client_portal
has_feature = access.plan_has_feature("client_portal")
print(f'   Has client_portal feature: {has_feature}')

# Vérifier manuellement
features = access.plan_features
print(f'   Client portal in features: {features.get("client_portal")}')

# Comparer avec la config du plan
plan_config = get_plan_config(access.plan_code)
print(f'   Plan config features: {plan_config.get("features", {})}')
print(f'   Plan config client_portal: {plan_config.get("features", {}).get("client_portal")}')
