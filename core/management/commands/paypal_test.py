"""
Management command to test PayPal API connectivity.

Usage:
    python manage.py paypal_test
    python manage.py paypal_test --mode=sandbox
    python manage.py paypal_test --mode=live
"""

from django.core.management.base import BaseCommand

from core.services_paypal_api import test_oauth_token, test_plan
from core.services_platform import get_paypal_config


class Command(BaseCommand):
    help = "Test PayPal API connectivity (OAuth token + plan validation)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode", type=str, default="",
            help="Force mode: sandbox or live (default: use DB setting)",
        )

    def handle(self, *args, **options):
        cfg = get_paypal_config()
        mode = options["mode"] or cfg["mode"]

        self.stdout.write(self.style.NOTICE(f"\n{'='*50}"))
        self.stdout.write(self.style.NOTICE(f"  PayPal API Test — mode: {mode}"))
        self.stdout.write(self.style.NOTICE(f"{'='*50}\n"))

        # 1) Config check
        self.stdout.write("Config:")
        self.stdout.write(f"  API base:    {cfg['api_base']}")
        self.stdout.write(f"  Client ID:   {cfg['client_id'][:12]}..." if cfg['client_id'] else "  Client ID:   (vide)")
        self.stdout.write(f"  Secret:      {'***' if cfg['client_secret'] else '(vide)'}")
        self.stdout.write(f"  Plan ID:     {cfg['plan_id'] or '(vide)'}")
        self.stdout.write(f"  Webhook URL: {cfg['webhook_url'] or '(vide)'}")
        self.stdout.write(f"  PayPal auto: {'ON' if cfg['enable_paypal_auto'] else 'OFF'}")
        self.stdout.write("")

        # 2) OAuth token test
        self.stdout.write("Test 1: OAuth Token...")
        result = test_oauth_token()
        if result["ok"]:
            self.stdout.write(self.style.SUCCESS(f"  OK — {result['message']}"))
        else:
            self.stdout.write(self.style.ERROR(f"  KO — {result['message']}"))
            self.stdout.write(self.style.WARNING("\nArrêt: impossible de continuer sans token."))
            return

        # 3) Plan validation
        if cfg["plan_id"]:
            self.stdout.write(f"\nTest 2: Plan validation ({cfg['plan_id']})...")
            result = test_plan(cfg["plan_id"])
            if result["ok"]:
                self.stdout.write(self.style.SUCCESS(f"  OK — {result['message']}"))
            else:
                self.stdout.write(self.style.ERROR(f"  KO — {result['message']}"))
        else:
            self.stdout.write(self.style.WARNING("\nTest 2: Plan validation — SKIP (aucun Plan ID configuré)"))

        self.stdout.write(self.style.NOTICE(f"\n{'='*50}"))
        self.stdout.write(self.style.SUCCESS("  Tests terminés."))
        self.stdout.write(self.style.NOTICE(f"{'='*50}\n"))
