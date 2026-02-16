import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import Agency, AgencyAccess
from agencies.services import get_agency_access
from clients.views_portal import _portal_enabled

# Tester pour l'agence agence-business
agency = Agency.objects.get(slug='agence-business')
print(f'🏢 Agence: {agency.name} ({agency.slug})')
print(f'   Public enabled: {agency.public_enabled}')
print(f'   Is active: {agency.is_active}')

# Tester la fonction _portal_enabled directement
portal_enabled = _portal_enabled(agency)
print(f'   _portal_enabled(): {portal_enabled}')

# Tester manuellement étape par étape
access = get_agency_access(agency)
print(f'   Access: {access}')
print(f'   Plan code: {access.plan_code}')
print(f'   plan_features: {access.plan_features}')
print(f'   plan_has_feature("client_portal"): {access.plan_has_feature("client_portal")}')
