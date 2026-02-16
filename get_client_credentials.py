import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from clients.models import ClientAccount
from django.contrib.auth.hashers import make_password

# Récupérer le premier compte client
client = ClientAccount.objects.first()
if client:
    client.password = make_password('test123')
    client.save()
    print(f'Email: {client.email}')
    print(f'Agence: {client.agency.slug}')
    print(f'Mot de passe: test123')
    print(f'URL: http://localhost:8000/a/{client.agency.slug}/c/login/')
else:
    print('Aucun compte client trouvé')
