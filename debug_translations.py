import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['DJANGO_DEBUG'] = '1'
django.setup()

from django.utils import translation

# Test spécifique pour Campagnes IA
with translation.override('es'):
    translated = translation.gettext("Campagnes IA")
    print(f'"Campagnes IA" en espagnol: "{translated}"')
    
    translated = translation.gettext("Campagnes IA — Marketing Engine")
    print(f'"Campagnes IA — Marketing Engine" en espagnol: "{translated}"')
    
    translated = translation.gettext("Nouvelle campagne")
    print(f'"Nouvelle campagne" en espagnol: "{translated}"')

with translation.override('en'):
    translated = translation.gettext("Campagnes IA")
    print(f'"Campagnes IA" en anglais: "{translated}"')

with translation.override('ht'):
    translated = translation.gettext("Campagnes IA")
    print(f'"Campagnes IA" en haïtien: "{translated}"')
