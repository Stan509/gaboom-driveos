from django.core.management.base import BaseCommand

from core.email import send_email


class Command(BaseCommand):
    help = "Send a test email using Brevo v3 API wrapper and print status."

    def add_arguments(self, parser):
        parser.add_argument("recipient", type=str)

    def handle(self, *args, **options):
        recipient = (options.get("recipient") or "").strip()
        if not recipient:
            self.stderr.write("recipient is required")
            return

        result = send_email(
            to_email=recipient,
            subject="Gaboom DriveOS — Brevo test",
            html_content="<p>Brevo test email sent from manage.py command.</p>",
        )
        self.stdout.write(str(result))
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS("OK"))
        else:
            self.stdout.write(self.style.ERROR("FAILED"))
