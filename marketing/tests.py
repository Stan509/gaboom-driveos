"""
Integration tests for Marketing Engine 2.0.
Covers: models, AI engine, bandit, views (CRUD, send, tracking, conversion).
"""
import json
import uuid

from django.test import TestCase, Client as HttpClient, override_settings
from django.urls import reverse

from agencies.models import Agency
from agencies.services import apply_plan_to_access, get_agency_access
from clients.models import ClientAccount
from core.models import User
from marketing.models import (
    MktCampaign, CampaignVariant, CampaignSend,
    MarketingTemplate, AutomationRule, BanditArm, WhatsAppOutbox,
)
from marketing.ai_engine import (
    generate_message, rewrite_message, score_message, suggest_improvements,
)
from marketing import bandit


# ═══════════════════════════ HELPERS ══════════════════════════════════

def _setup_agency_user():
    """Create an agency + admin user for testing."""
    agency = Agency.objects.create(name="Test Agency", slug="test-agency")
    agency.marketing_email_from = "no-reply@test-agency.com"
    agency.marketing_whatsapp_phone_id = "1234567890"
    agency.set_marketing_email_api_key("test_key")
    agency.set_marketing_whatsapp_api_key("test_key")
    agency.save()
    user = User.objects.create_user(
        username="testadmin",
        email="admin@test.com",
        password="testpass123",
        agency=agency,
        role="agency_owner",
        email_verified=True,
    )
    access = get_agency_access(agency)
    apply_plan_to_access(access, "business")
    return agency, user


# ═══════════════════════════ MODEL TESTS ═════════════════════════════

class MktCampaignModelTest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()

    def test_create_campaign(self):
        c = MktCampaign.objects.create(
            agency=self.agency, name="Summer Promo",
            objective="promo", channel_email=True, channel_whatsapp=False,
        )
        self.assertEqual(c.status, "draft")
        self.assertEqual(str(c), "Summer Promo (Brouillon)")

    def test_create_variant(self):
        c = MktCampaign.objects.create(agency=self.agency, name="Test")
        v = CampaignVariant.objects.create(
            campaign=c, variant="A", body_text="Hello {nom}",
            style="simple", score=75,
        )
        self.assertEqual(v.score, 75)
        self.assertTrue(v.is_active)

    def test_ab_variants(self):
        c = MktCampaign.objects.create(
            agency=self.agency, name="AB Test", ab_enabled=True,
        )
        CampaignVariant.objects.create(campaign=c, variant="A", body_text="Version A")
        CampaignVariant.objects.create(campaign=c, variant="B", body_text="Version B")
        self.assertEqual(c.variants.count(), 2)

    def test_campaign_send_token(self):
        c = MktCampaign.objects.create(agency=self.agency, name="Test")
        v = CampaignVariant.objects.create(campaign=c, variant="A", body_text="Hi")
        client = ClientAccount.objects.create(
            agency=self.agency, full_name="Jean", email="jean@test.com",
        )
        send = CampaignSend.objects.create(
            campaign=c, variant=v, client=client, channel="email",
        )
        self.assertIsNotNone(send.token)
        self.assertIsInstance(send.token, uuid.UUID)

    def test_whatsapp_outbox(self):
        c = MktCampaign.objects.create(agency=self.agency, name="WA Test")
        client = ClientAccount.objects.create(
            agency=self.agency, full_name="Marie", email="marie@test.com",
            phone="+33612345678",
        )
        wa = WhatsAppOutbox.objects.create(
            agency=self.agency, campaign=c, client=client,
            phone="+33612345678", message="Bonjour Marie",
            wa_link="https://wa.me/33612345678?text=Bonjour",
        )
        self.assertEqual(wa.status, "pending")

    def test_automation_rule(self):
        rule = AutomationRule.objects.create(
            agency=self.agency, name="Welcome",
            key="booking_confirmed", enabled=True,
            channel="email", delay_minutes=120,
        )
        self.assertEqual(rule.delay_hours, 2)
        self.assertEqual(rule.get_trigger_display(), "Confirmation réservation")

    def test_bandit_arm(self):
        arm = BanditArm.objects.create(
            agency=self.agency, arm_key="promo_simple_A",
            pulls=100, rewards=15,
        )
        self.assertAlmostEqual(arm.conversion_rate, 0.15)


# ═══════════════════════════ AI ENGINE TESTS ═════════════════════════

class AIEngineTest(TestCase):
    def test_generate_message(self):
        text = generate_message(
            objective="promo", style="simple", channel="email",
            agence="Test Agency",
        )
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 10)

    def test_generate_with_variables(self):
        text = generate_message(
            objective="promo", style="simple", channel="email",
            offre="-20%", voiture="BMW X5", cta_link="https://test.com",
            agence="Test Agency",
        )
        self.assertIn("-20%", text)

    def test_rewrite_shorter(self):
        original = "Ceci est un message marketing assez long pour tester la fonctionnalite de raccourcissement du texte."
        result = rewrite_message("shorter", original)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_rewrite_luxury(self):
        original = "Bonjour, voici notre offre."
        result = rewrite_message("luxury", original)
        self.assertIsInstance(result, str)

    def test_score_message(self):
        text = "Bonjour {nom}, profitez de notre offre exclusive -20% sur la BMW X5. Reservez maintenant : {lien}"
        result = score_message(text)
        self.assertIn("total", result)
        self.assertIn("grade", result)
        self.assertIn("breakdown", result)
        self.assertIsInstance(result["total"], int)
        self.assertGreaterEqual(result["total"], 0)
        self.assertLessEqual(result["total"], 100)
        self.assertIn(result["grade"], ["A", "B", "C", "D", "F"])

    def test_suggest_improvements(self):
        text = "salut"
        suggestions = suggest_improvements(text)
        self.assertIsInstance(suggestions, list)

    def test_score_empty_text(self):
        result = score_message("")
        self.assertLessEqual(result["total"], 10)


# ═══════════════════════════ BANDIT TESTS ════════════════════════════

class BanditTest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()

    def test_record_pull(self):
        bandit.record_pull(self.agency, "test_arm_1")
        arm = BanditArm.objects.get(agency=self.agency, arm_key="test_arm_1")
        self.assertEqual(arm.pulls, 1)

    def test_record_reward(self):
        bandit.record_pull(self.agency, "test_arm_2")
        bandit.record_reward(self.agency, "test_arm_2", converted=True)
        arm = BanditArm.objects.get(agency=self.agency, arm_key="test_arm_2")
        self.assertEqual(arm.rewards, 1)

    def test_select_arm(self):
        for key in ["arm_a", "arm_b", "arm_c"]:
            BanditArm.objects.create(
                agency=self.agency, arm_key=key, pulls=10, rewards=2,
            )
        arms = list(BanditArm.objects.filter(agency=self.agency))
        selected = bandit.select_arm(self.agency, arms)
        self.assertIn(selected.arm_key, ["arm_a", "arm_b", "arm_c"])

    def test_get_arm_stats(self):
        BanditArm.objects.create(
            agency=self.agency, arm_key="stat_arm", pulls=50, rewards=10,
        )
        stats = bandit.get_arm_stats(self.agency)
        self.assertIsInstance(stats, list)
        self.assertGreater(len(stats), 0)


# ═══════════════════════════ VIEW TESTS ══════════════════════════════

@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
class CampaignViewTest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()
        self.client = HttpClient()
        self.client.login(username="testadmin", password="testpass123")

    def test_campaign_list_page(self):
        resp = self.client.get(reverse("dashboard:mkt_campaign_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Campagnes IA")

    def test_campaign_create_page(self):
        resp = self.client.get(reverse("dashboard:mkt_campaign_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Assistant IA")

    def test_campaign_create_post(self):
        resp = self.client.post(reverse("dashboard:mkt_campaign_create"), {
            "name": "Test Campaign",
            "objective": "promo",
            "channel_email": "on",
            "target": "all_clients",
            "body_a": "Bonjour {nom}, profitez de notre offre !",
            "subject_a": "Offre speciale",
            "style_a": "simple",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(MktCampaign.objects.filter(name="Test Campaign").exists())
        campaign = MktCampaign.objects.get(name="Test Campaign")
        self.assertEqual(campaign.variants.count(), 1)

    def test_campaign_create_ab(self):
        resp = self.client.post(reverse("dashboard:mkt_campaign_create"), {
            "name": "AB Campaign",
            "objective": "relance",
            "channel_email": "on",
            "target": "all_clients",
            "ab_enabled": "on",
            "body_a": "Version A",
            "subject_a": "Subject A",
            "style_a": "simple",
            "body_b": "Version B",
            "subject_b": "Subject B",
            "style_b": "urgent",
        })
        self.assertEqual(resp.status_code, 302)
        campaign = MktCampaign.objects.get(name="AB Campaign")
        self.assertTrue(campaign.ab_enabled)
        self.assertEqual(campaign.variants.count(), 2)

    def test_campaign_edit(self):
        c = MktCampaign.objects.create(agency=self.agency, name="Edit Me")
        CampaignVariant.objects.create(campaign=c, variant="A", body_text="Old")
        resp = self.client.get(reverse("dashboard:mkt_campaign_edit", args=[c.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_campaign_edit_post(self):
        c = MktCampaign.objects.create(agency=self.agency, name="Edit Me")
        CampaignVariant.objects.create(campaign=c, variant="A", body_text="Old")
        resp = self.client.post(reverse("dashboard:mkt_campaign_edit", args=[c.pk]), {
            "name": "Edited Campaign",
            "objective": "promo",
            "channel_email": "on",
            "target": "all_clients",
            "body_a": "New content",
            "subject_a": "New subject",
            "style_a": "luxe",
        })
        self.assertEqual(resp.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.name, "Edited Campaign")

    def test_campaign_delete(self):
        c = MktCampaign.objects.create(agency=self.agency, name="Delete Me")
        resp = self.client.post(reverse("dashboard:mkt_campaign_delete", args=[c.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MktCampaign.objects.filter(pk=c.pk).exists())

    def test_campaign_send(self):
        c = MktCampaign.objects.create(
            agency=self.agency, name="Send Test",
            channel_email=True, channel_whatsapp=True,
        )
        CampaignVariant.objects.create(
            campaign=c, variant="A", body_text="Hello {nom}",
        )
        ClientAccount.objects.create(
            agency=self.agency, full_name="Client1",
            email="c1@test.com", phone="+33600000001",
        )
        ClientAccount.objects.create(
            agency=self.agency, full_name="Client2",
            email="c2@test.com", phone="+33600000002",
        )
        resp = self.client.post(reverse("dashboard:mkt_campaign_send", args=[c.pk]))
        self.assertEqual(resp.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.status, "running")
        self.assertGreater(CampaignSend.objects.filter(campaign=c).count(), 0)
        self.assertGreater(WhatsAppOutbox.objects.filter(campaign=c).count(), 0)


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
class AutomationViewTest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()
        self.client = HttpClient()
        self.client.login(username="testadmin", password="testpass123")

    def test_automations_page(self):
        resp = self.client.get(reverse("dashboard:mkt_automations"))
        self.assertEqual(resp.status_code, 200)

    def test_automation_create(self):
        resp = self.client.post(reverse("dashboard:mkt_automation_create"), {
            "name": "Welcome Rule",
            "trigger": "booking_confirmed",
            "channel": "email",
            "delay_hours": "2",
            "enabled": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AutomationRule.objects.filter(agency=self.agency).exists())

    def test_automation_toggle(self):
        rule = AutomationRule.objects.create(
            agency=self.agency, key="booking_confirmed", enabled=False,
        )
        resp = self.client.post(
            reverse("dashboard:mkt_automation_toggle", args=[rule.pk]),
            {"enabled": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        rule.refresh_from_db()
        self.assertTrue(rule.enabled)

    def test_automation_delete(self):
        rule = AutomationRule.objects.create(
            agency=self.agency, key="booking_confirmed",
        )
        resp = self.client.post(
            reverse("dashboard:mkt_automation_delete", args=[rule.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(AutomationRule.objects.filter(pk=rule.pk).exists())


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
class AnalyticsViewTest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()
        self.client = HttpClient()
        self.client.login(username="testadmin", password="testpass123")

    def test_analytics_page_7d(self):
        resp = self.client.get(reverse("dashboard:mkt_analytics") + "?period=7")
        self.assertEqual(resp.status_code, 200)

    def test_analytics_page_30d(self):
        resp = self.client.get(reverse("dashboard:mkt_analytics") + "?period=30")
        self.assertEqual(resp.status_code, 200)


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
class WAOutboxViewTest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()
        self.client = HttpClient()
        self.client.login(username="testadmin", password="testpass123")

    def test_wa_outbox_page(self):
        resp = self.client.get(reverse("dashboard:mkt_wa_outbox"))
        self.assertEqual(resp.status_code, 200)

    def test_wa_outbox_filter(self):
        resp = self.client.get(reverse("dashboard:mkt_wa_outbox") + "?status=pending")
        self.assertEqual(resp.status_code, 200)

    def test_wa_mark_sent(self):
        c = MktCampaign.objects.create(agency=self.agency, name="WA")
        cl = ClientAccount.objects.create(
            agency=self.agency, full_name="Test", email="wa@test.com",
        )
        wa = WhatsAppOutbox.objects.create(
            agency=self.agency, campaign=c, client=cl,
            phone="+33600000000", message="Hello",
        )
        resp = self.client.post(reverse("dashboard:mkt_wa_mark_sent", args=[wa.pk]))
        self.assertEqual(resp.status_code, 200)
        wa.refresh_from_db()
        self.assertEqual(wa.status, "sent")
        self.assertIsNotNone(wa.sent_at)


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ]
)
class AIWriterAPITest(TestCase):
    def setUp(self):
        self.agency, self.user = _setup_agency_user()
        self.client = HttpClient()
        self.client.login(username="testadmin", password="testpass123")

    def test_generate(self):
        resp = self.client.post(
            reverse("dashboard:mkt_api_ai"),
            json.dumps({"action": "generate", "objective": "promo", "style": "simple", "channel": "email"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("text", data)
        self.assertIn("score", data)

    def test_rewrite(self):
        resp = self.client.post(
            reverse("dashboard:mkt_api_ai"),
            json.dumps({"action": "rewrite", "mode": "shorter", "text": "Un long message marketing pour tester."}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("text", data)

    def test_score(self):
        resp = self.client.post(
            reverse("dashboard:mkt_api_ai"),
            json.dumps({"action": "score", "text": "Bonjour {nom}, reservez votre {voiture} maintenant !"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("score", data)
        self.assertIn("total", data["score"])

    def test_invalid_action(self):
        resp = self.client.post(
            reverse("dashboard:mkt_api_ai"),
            json.dumps({"action": "invalid"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ═══════════════════════════ CLICK TRACKING ══════════════════════════

class ClickTrackingTest(TestCase):
    def setUp(self):
        self.agency, _ = _setup_agency_user()

    def test_click_tracking(self):
        c = MktCampaign.objects.create(agency=self.agency, name="Track Test")
        v = CampaignVariant.objects.create(campaign=c, variant="A", body_text="Hi")
        cl = ClientAccount.objects.create(
            agency=self.agency, full_name="Tracker", email="track@test.com",
        )
        send = CampaignSend.objects.create(
            campaign=c, variant=v, client=cl, channel="email",
            meta={"redirect_url": "/a/test-agency/"},
        )
        token = str(send.token)
        http = HttpClient()
        resp = http.get(f"/t/{token}/")
        self.assertEqual(resp.status_code, 302)
        send.refresh_from_db()
        self.assertIsNotNone(send.clicked_at)

    def test_click_tracking_invalid_token(self):
        http = HttpClient()
        resp = http.get("/t/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(resp.status_code, 404)

    def test_click_tracking_bad_format(self):
        http = HttpClient()
        resp = http.get("/t/not-a-uuid/")
        self.assertEqual(resp.status_code, 404)


# ═══════════════════════════ CONVERSION HOOK ═════════════════════════

class ConversionHookTest(TestCase):
    def setUp(self):
        self.agency, _ = _setup_agency_user()

    def test_conversion_recording(self):
        from dashboard.views_marketing import record_conversion_from_reservation

        c = MktCampaign.objects.create(agency=self.agency, name="Conv Test")
        v = CampaignVariant.objects.create(campaign=c, variant="A", body_text="Hi")
        cl = ClientAccount.objects.create(
            agency=self.agency, full_name="Converter", email="conv@test.com",
        )
        send = CampaignSend.objects.create(
            campaign=c, variant=v, client=cl, channel="email",
            meta={"arm_key": "promo_simple_A"},
        )
        bandit.record_pull(self.agency, "promo_simple_A")

        # Simulate a reservation with utm_token
        class FakeReservation:
            utm_token = str(send.token)

        record_conversion_from_reservation(FakeReservation())

        send.refresh_from_db()
        self.assertIsNotNone(send.converted_at)

        arm = BanditArm.objects.get(agency=self.agency, arm_key="promo_simple_A")
        self.assertEqual(arm.rewards, 1)

    def test_conversion_no_token(self):
        from dashboard.views_marketing import record_conversion_from_reservation

        class FakeReservation:
            utm_token = None

        # Should not raise
        record_conversion_from_reservation(FakeReservation())


# ═══════════════════════════ SEED TEMPLATES ══════════════════════════

class SeedTemplatesTest(TestCase):
    def test_seed_creates_templates(self):
        from django.core.management import call_command
        call_command("seed_mkt_templates")
        self.assertGreaterEqual(MarketingTemplate.objects.filter(agency__isnull=True).count(), 10)

    def test_seed_idempotent(self):
        from django.core.management import call_command
        call_command("seed_mkt_templates")
        call_command("seed_mkt_templates")
        self.assertEqual(
            MarketingTemplate.objects.filter(agency__isnull=True).count(), 10,
        )
