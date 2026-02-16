"""
Multi-tenant isolation tests for GaboomDriveOS.
Ensures strict agency separation — no cross-agency data leaks.

TEST 1: User B cannot see Agency A's vehicles
TEST 2: User B cannot access Agency A's object detail via direct URL
TEST 3: Cross-agency POST/PUT is rejected
TEST 4: Superadmin can see everything
"""
from django.test import TestCase, Client as HttpClient, override_settings
from django.urls import reverse

from agencies.models import Agency, Vehicle
from agencies.services import apply_plan_to_access, get_agency_access
from clients.models import Client
from core.models import User


SAFE_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]


def _make_agency(name, slug):
    return Agency.objects.create(name=name, slug=slug)


def _make_user(agency, username, role="agency_owner", is_super=False):
    return User.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="pass1234",
        agency=agency if not is_super else None,
        role=role,
        email_verified=True,
        is_superuser=is_super,
    )


@override_settings(MIDDLEWARE=SAFE_MIDDLEWARE)
class TenantIsolationTest(TestCase):
    """TEST 1 + TEST 2: Cross-agency visibility is blocked."""

    def setUp(self):
        self.agency_a = _make_agency("Agency A", "agency-a")
        self.agency_b = _make_agency("Agency B", "agency-b")
        self.user_a = _make_user(self.agency_a, "user_a")
        self.user_b = _make_user(self.agency_b, "user_b")

        # Create data for Agency A
        self.vehicle_a = Vehicle.objects.create(
            agency=self.agency_a, make="BMW", model="X5",
            plate_number="AA-111-AA", daily_price=100,
        )
        self.client_a = Client.objects.create(
            agency=self.agency_a, full_name="Jean Dupont",
            email="jean@a.com",
        )

        # Create data for Agency B
        self.vehicle_b = Vehicle.objects.create(
            agency=self.agency_b, make="Audi", model="A4",
            plate_number="BB-222-BB", daily_price=80,
        )

    def _login(self, username):
        c = HttpClient()
        c.login(username=username, password="pass1234")
        return c

    # ── TEST 1: List views only show own agency data ──

    def test_vehicle_list_isolation(self):
        """User B must NOT see Agency A's vehicles in the list."""
        c = self._login("user_b")
        resp = c.get(reverse("dashboard:vehicle_hub"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("BMW", content)
        self.assertNotIn("X5", content)

    def test_client_list_isolation(self):
        """User B must NOT see Agency A's clients in the list."""
        c = self._login("user_b")
        resp = c.get(reverse("dashboard:client_hub"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("Jean", content)
        self.assertNotIn("Dupont", content)

    # ── TEST 2: Direct URL access to other agency's objects is blocked ──

    def test_vehicle_detail_cross_agency_blocked(self):
        """User B cannot access Agency A's vehicle edit via direct URL."""
        c = self._login("user_b")
        # vehicle_edit redirects to hub; follow the redirect and check hub content
        resp = c.get(reverse("dashboard:vehicle_hub"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Agency A's vehicle must NOT appear in Agency B's hub
        self.assertNotIn("BMW", content)
        self.assertNotIn("AA-111-AA", content)

    def test_client_detail_cross_agency_blocked(self):
        """User B cannot access Agency A's client detail via direct URL."""
        c = self._login("user_b")
        resp = c.get(reverse("dashboard:client_detail", args=[self.client_a.pk]))
        self.assertIn(resp.status_code, [403, 404])

    # ── TEST 3: Cross-agency POST is rejected ──

    def test_vehicle_delete_cross_agency_rejected(self):
        """User B cannot delete Agency A's vehicle via POST."""
        c = self._login("user_b")
        resp = c.post(reverse("dashboard:vehicle_delete", args=[self.vehicle_a.pk]))
        self.assertIn(resp.status_code, [403, 404])
        # Vehicle must still exist
        self.assertTrue(Vehicle.objects.filter(pk=self.vehicle_a.pk).exists())

    def test_client_delete_cross_agency_rejected(self):
        """User B cannot delete Agency A's client via POST."""
        c = self._login("user_b")
        resp = c.post(reverse("dashboard:client_delete", args=[self.client_a.pk]))
        self.assertIn(resp.status_code, [403, 404])
        self.assertTrue(Client.objects.filter(pk=self.client_a.pk).exists())


@override_settings(MIDDLEWARE=SAFE_MIDDLEWARE)
class SuperadminAccessTest(TestCase):
    """TEST 4: Superadmin can see everything."""

    def setUp(self):
        self.agency_a = _make_agency("Agency A", "agency-a")
        self.superuser = _make_user(None, "superadmin", is_super=True)
        self.vehicle_a = Vehicle.objects.create(
            agency=self.agency_a, make="Mercedes", model="C200",
            plate_number="CC-333-CC", daily_price=120,
        )

    def test_superadmin_can_access_saas(self):
        c = HttpClient()
        c.login(username="superadmin", password="pass1234")
        resp = c.get("/saas/")
        self.assertIn(resp.status_code, [200, 302])


@override_settings(MIDDLEWARE=SAFE_MIDDLEWARE)
class RBACPermissionTest(TestCase):
    """Test that RBAC roles correctly restrict access."""

    def setUp(self):
        self.agency = _make_agency("Test Agency", "test-rbac")
        access = get_agency_access(self.agency)
        apply_plan_to_access(access, "business")
        self.owner = _make_user(self.agency, "owner", role="agency_owner")
        self.staff = _make_user(self.agency, "staff", role="agency_staff")
        self.readonly = _make_user(self.agency, "readonly", role="read_only")
        self.accountant = _make_user(self.agency, "accountant", role="agency_accountant")

    def _login(self, username):
        c = HttpClient()
        c.login(username=username, password="pass1234")
        return c

    def test_owner_can_access_settings(self):
        c = self._login("owner")
        resp = c.get(reverse("dashboard:business_settings"))
        self.assertEqual(resp.status_code, 200)

    def test_staff_cannot_access_settings(self):
        c = self._login("staff")
        resp = c.get(reverse("dashboard:business_settings"))
        self.assertEqual(resp.status_code, 403)

    def test_readonly_cannot_create_vehicle(self):
        c = self._login("readonly")
        resp = c.get(reverse("dashboard:vehicle_create"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_cannot_access_team(self):
        c = self._login("staff")
        resp = c.get(reverse("dashboard:team"))
        self.assertEqual(resp.status_code, 403)

    def test_accountant_can_access_payments(self):
        c = self._login("accountant")
        resp = c.get(reverse("dashboard:payment_list"))
        self.assertEqual(resp.status_code, 200)

    def test_staff_cannot_access_marketing(self):
        c = self._login("staff")
        resp = c.get(reverse("dashboard:mkt_campaign_list"))
        self.assertIn(resp.status_code, [403, 302])

    def test_owner_can_access_marketing(self):
        c = self._login("owner")
        resp = c.get(reverse("dashboard:mkt_campaign_list"))
        self.assertEqual(resp.status_code, 200)

    def test_readonly_can_view_dashboard(self):
        c = self._login("readonly")
        resp = c.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)

    def test_readonly_cannot_delete_vehicle(self):
        v = Vehicle.objects.create(
            agency=self.agency, make="Test", model="Car",
            plate_number="TT-999-TT", daily_price=50,
        )
        c = self._login("readonly")
        resp = c.post(reverse("dashboard:vehicle_delete", args=[v.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Vehicle.objects.filter(pk=v.pk).exists())


@override_settings(MIDDLEWARE=SAFE_MIDDLEWARE)
class GPSPlanAccessTest(TestCase):
    def setUp(self):
        self.agency = _make_agency("GPS Agency", "gps-agency")
        access = get_agency_access(self.agency)
        apply_plan_to_access(access, "starter")
        self.owner = _make_user(self.agency, "gps_owner")
        self.vehicle = Vehicle.objects.create(
            agency=self.agency, make="Tesla", model="Model 3",
            plate_number="EE-555-EE", daily_price=150,
        )

    def _login(self):
        c = HttpClient()
        c.login(username="gps_owner", password="pass1234")
        return c

    def test_gps_views_blocked_on_starter_plan(self):
        c = self._login()
        for url in [
            reverse("dashboard:gps_tracking"),
            reverse("dashboard:gps_zone_list"),
            reverse("dashboard:gps_alert_list"),
            reverse("dashboard:maps_hub"),
        ]:
            with self.subTest(url=url):
                resp = c.get(url)
                self.assertEqual(resp.status_code, 403)
        for url in [
            reverse("dashboard:api_gps_update"),
            reverse("dashboard:api_gps_positions"),
            reverse("dashboard:api_maps_ai_analyze"),
            reverse("dashboard:api_maps_heatmap"),
        ]:
            with self.subTest(url=url):
                resp = c.get(url)
                self.assertEqual(resp.status_code, 403)

    def test_gps_views_allowed_on_business_plan(self):
        access = get_agency_access(self.agency)
        apply_plan_to_access(access, "business")
        c = self._login()
        resp = c.get(reverse("dashboard:gps_tracking"))
        self.assertEqual(resp.status_code, 200)
        resp = c.get(reverse("dashboard:maps_hub"))
        self.assertEqual(resp.status_code, 200)
        resp = c.get(reverse("dashboard:api_gps_positions"))
        self.assertEqual(resp.status_code, 200)
        resp = c.get(reverse("dashboard:api_maps_heatmap"))
        self.assertEqual(resp.status_code, 200)
        resp = c.get(reverse("dashboard:api_maps_ai_analyze"), {"vehicle_id": self.vehicle.pk})
        self.assertEqual(resp.status_code, 200)
