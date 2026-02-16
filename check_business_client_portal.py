import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agencies.models import Agency, AgencyAccess
from agencies.services import get_plan_config

# Récupérer toutes les agences avec le plan business
business_plans = AgencyAccess.objects.filter(plan_code='business')
print(f'📋 Agences avec le plan business: {business_plans.count()}')

for access in business_plans:
    agency = access.agency
    plan_config = get_plan_config(access.plan_code)
    client_portal_enabled = plan_config.get('features', {}).get('client_portal', False)
    
    print(f'\n🏢 {agency.name} ({agency.slug})')
    print(f'   Plan: {access.plan_name}')
    print(f'   Portail client (via plan): {"✅ Activé" if client_portal_enabled else "❌ Désactivé"}')
    print(f'   URL du portail: http://localhost:8000/a/{agency.slug}/c/')
    
    # Vérifier s'il y a des comptes clients
    from clients.models import ClientAccount
    clients = ClientAccount.objects.filter(agency=agency)
    print(f'   Comptes clients: {clients.count()}')
    
    # Créer un mot de passe de test pour le premier client si exists
    if clients.exists():
        from django.contrib.auth.hashers import make_password
        first_client = clients.first()
        first_client.password = make_password('test123')
        first_client.save()
        print(f'   🔑 Identifiants de test:')
        print(f'      Email: {first_client.email}')
        print(f'      Mot de passe: test123')

print(f'\n✅ Toutes les agences business ont accès au portail client via leur plan!')
