# Generated migration for username field population

from django.db import migrations


def populate_username(apps, schema_editor):
    """Populate username field with full_name for existing accounts."""
    ClientAccount = apps.get_model('clients', 'ClientAccount')
    
    for account in ClientAccount.objects.filter(username__isnull=True):
        # Create username from full_name: lowercase, replace spaces with underscores
        username = account.full_name.lower().replace(' ', '_')
        base_username = username
        
        # Ensure uniqueness within agency
        counter = 1
        while ClientAccount.objects.filter(agency=account.agency, username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        
        account.username = username
        account.save(update_fields=['username'])


def reverse_populate_username(apps, schema_editor):
    """Reverse: set username to None for all accounts."""
    ClientAccount = apps.get_model('clients', 'ClientAccount')
    ClientAccount.objects.all().update(username=None)


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0008_add_username_field'),
    ]

    operations = [
        migrations.RunPython(populate_username, reverse_populate_username),
    ]
