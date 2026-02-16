from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from agencies.models import Agency

User = get_user_model()

class Command(BaseCommand):
    help = "Wipe database and create superadmin"

    def handle(self, *args, **options):
        self.stdout.write("Wiping database...")
        # Deleting agencies should cascade to vehicles, clients, etc.
        Agency.objects.all().delete()
        # Deleting users
        User.objects.all().delete()
        
        self.stdout.write("Creating superadmin...")
        User.objects.create_superuser(
            username="admin",
            email="admin@gaboom.com",
            password="adminpassword"
        )
        self.stdout.write(self.style.SUCCESS("Superadmin created.\nUsername: admin\nEmail: admin@gaboom.com\nPassword: adminpassword"))
