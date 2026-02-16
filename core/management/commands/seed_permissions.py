"""
Management command to seed the Permission table from ALL_PERMISSIONS.

Usage:
    python manage.py seed_permissions
"""

from django.core.management.base import BaseCommand

from agencies.models import Permission
from core.permissions import ALL_PERMISSIONS


class Command(BaseCommand):
    help = "Seed (or sync) the Permission table from ALL_PERMISSIONS in core/permissions.py"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        existing_keys = set()

        for key, label, group in ALL_PERMISSIONS:
            obj, created = Permission.objects.update_or_create(
                key=key,
                defaults={"label": label, "group": group},
            )
            existing_keys.add(key)
            if created:
                created_count += 1
            else:
                updated_count += 1

        # Remove stale permissions no longer in ALL_PERMISSIONS
        stale = Permission.objects.exclude(key__in=existing_keys)
        stale_count = stale.count()
        if stale_count:
            stale.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Permissions synced: {created_count} created, "
                f"{updated_count} updated, {stale_count} removed."
            )
        )
