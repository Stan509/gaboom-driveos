from django.core.management.base import BaseCommand

from agencies.models import Agency
from public_site.models import PublicPage
from public_site.signals import DEFAULT_PAGES


class Command(BaseCommand):
    help = "Create missing default CMS pages for all existing agencies."

    def handle(self, *args, **options):
        agencies = Agency.objects.all()
        total_created = 0

        for agency in agencies:
            existing_slugs = set(
                PublicPage.objects.filter(agency=agency).values_list("slug", flat=True)
            )
            created = 0
            for page_data in DEFAULT_PAGES:
                if page_data["slug"] in existing_slugs:
                    continue
                content = page_data["content"].replace("{{ agency }}", agency.name)
                PublicPage.objects.create(
                    agency=agency,
                    title=page_data["title"],
                    slug=page_data["slug"],
                    template_variant=page_data["template_variant"],
                    show_in_nav=page_data["show_in_nav"],
                    nav_order=page_data["nav_order"],
                    is_published=page_data["is_published"],
                    content=content,
                )
                created += 1

            if created:
                self.stdout.write(f"  {agency.slug}: +{created} pages")
                total_created += created
            else:
                self.stdout.write(f"  {agency.slug}: already complete")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Created {total_created} pages total."))
