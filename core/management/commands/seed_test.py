import os
import secrets
import string

from django.core.management.base import BaseCommand

from agencies.models import Agency, Vehicle
from core.models import User


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = (
        "Seed demo data (agency + vehicles). "
        "Requires ENABLE_DEMO_SEED=1 environment variable. "
        "Never creates a superuser — use 'createsuperuser' for that."
    )

    def handle(self, *args, **options):
        if os.environ.get("ENABLE_DEMO_SEED") != "1":
            self.stderr.write(
                self.style.ERROR(
                    "Demo seed is disabled. Set ENABLE_DEMO_SEED=1 to run."
                )
            )
            return

        agency, created = Agency.objects.get_or_create(
            slug="demo-agency",
            defaults={
                "name": "Demo Agency",
                "public_enabled": True,
                "maintenance_mode": False,
                "primary_color": "#6D28D9",
                "secondary_color": "#FACC15",
                "theme": "default",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Agency created: {agency.name}"))
        else:
            self.stdout.write(f"Agency already exists: {agency.name}")

        email = "demo@example.com"
        if not User.objects.filter(email=email).exists():
            password = _random_password()
            User.objects.create_user(
                username=email,
                email=email,
                password=password,
                role="owner",
                agency=agency,
                is_staff=False,
                is_superuser=False,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Demo user created: {email} / {password}")
            )
            self.stdout.write(
                self.style.WARNING("⚠ Save this password — it won't be shown again.")
            )
        else:
            self.stdout.write(f"Demo user already exists: {email}")

        Vehicle.objects.get_or_create(
            agency=agency,
            plate_number="AB-123-CD",
            defaults={
                "make": "Peugeot",
                "model": "208",
                "daily_price": 45.00,
                "status": "available",
                "public_visible": True,
            },
        )
        Vehicle.objects.get_or_create(
            agency=agency,
            plate_number="EF-456-GH",
            defaults={
                "make": "Renault",
                "model": "Clio V",
                "daily_price": 39.00,
                "status": "available",
                "public_visible": True,
            },
        )
        self.stdout.write(self.style.SUCCESS("Demo seed complete."))
