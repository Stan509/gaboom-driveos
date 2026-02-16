from django.core.management.base import BaseCommand

from agencies.models_access import AgencyAccess
from agencies.services import sync_access


class Command(BaseCommand):
    help = "Synchronise tous les AgencyAccess : suspend les agences expirées."

    def handle(self, *args, **options):
        all_access = AgencyAccess.objects.select_related("agency").all()
        total = all_access.count()
        trial = active = suspended = newly_suspended = 0

        for access in all_access.iterator():
            old_status = access.status
            sync_access(access)
            if access.status == "trial":
                trial += 1
            elif access.status == "active":
                active += 1
            elif access.status == "suspended":
                suspended += 1
                if old_status != "suspended":
                    newly_suspended += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  SUSPENDED: {access.agency.name} (was {old_status})"
                        )
                    )

        self.stdout.write(self.style.SUCCESS(
            f"\nSync terminé :\n"
            f"  Total      : {total}\n"
            f"  Trial      : {trial}\n"
            f"  Active     : {active}\n"
            f"  Suspended  : {suspended} ({newly_suspended} nouveau(x))"
        ))
