import hashlib
import json
import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify


class AgencyQuerySet(models.QuerySet):
    """Scoped queryset — always filter by agency."""

    def for_agency(self, agency):
        return self.filter(agency=agency)


class Agency(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=150, db_index=True)

    is_active = models.BooleanField(default=False)
    public_enabled = models.BooleanField(default=False)
    maintenance_mode = models.BooleanField(default=False)

    subscription_status = models.CharField(max_length=50, default="trial")

    primary_color = models.CharField(max_length=20, default="#6D28D9")
    secondary_color = models.CharField(max_length=20, default="#FACC15")

    theme = models.CharField(max_length=50, default="default")

    # ── Agency identity / profile ──
    logo = models.ImageField(upload_to="agencies/logos/", null=True, blank=True)
    legal_name = models.CharField(max_length=255, blank=True, default="")
    slogan = models.CharField(max_length=255, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    whatsapp = models.CharField(max_length=30, blank=True, default="")
    marketing_email_from = models.EmailField(blank=True, default="")
    marketing_email_api_key_encrypted = models.TextField(blank=True, default="")
    marketing_whatsapp_phone_id = models.CharField(max_length=64, blank=True, default="")
    marketing_whatsapp_api_key_encrypted = models.TextField(blank=True, default="")
    address_line1 = models.CharField(max_length=255, blank=True, default="")
    address_line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    website_url = models.URLField(max_length=500, blank=True, default="")
    tax_id = models.CharField(max_length=50, blank=True, default="")
    invoice_footer = models.TextField(blank=True, default="")
    agency_signature = models.ImageField(upload_to="agencies/signatures/", null=True, blank=True)

    public_headline = models.CharField(max_length=120, blank=True, default="")
    public_tagline = models.CharField(max_length=255, blank=True, default="")
    public_phone = models.CharField(max_length=30, blank=True, default="")
    public_whatsapp = models.CharField(max_length=30, blank=True, default="")
    public_city = models.CharField(max_length=100, blank=True, default="")
    public_logo_url = models.URLField(max_length=500, blank=True, default="")

    # ── Business settings (used by contracts) ──
    km_included_default = models.PositiveIntegerField(default=200)
    km_price_default = models.DecimalField(max_digits=6, decimal_places=2, default=0.30)
    fuel_fee_default = models.DecimalField(max_digits=8, decimal_places=2, default=30.00)
    late_fee_default = models.DecimalField(max_digits=8, decimal_places=2, default=50.00)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=5, default="EUR")
    maintenance_interval_km = models.PositiveIntegerField(default=10000)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "agency"
            slug = base
            i = 1
            while Agency.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        else:
            self.slug = slugify(self.slug)
        self.slug = self.slug.lower()[:150]
        super().save(*args, **kwargs)

    def _decrypt_secret(self, token: str) -> str:
        if not token:
            return ""
        try:
            from core.crypto import decrypt
            return decrypt(token)
        except Exception:
            return ""

    def _encrypt_secret(self, value: str) -> str:
        if not value:
            return ""
        from core.crypto import encrypt, ensure_fernet_key
        ensure_fernet_key()
        return encrypt(value)

    @property
    def marketing_email_api_key(self) -> str:
        return self._decrypt_secret(self.marketing_email_api_key_encrypted)

    def set_marketing_email_api_key(self, value: str):
        self.marketing_email_api_key_encrypted = self._encrypt_secret(value)

    @property
    def marketing_whatsapp_api_key(self) -> str:
        return self._decrypt_secret(self.marketing_whatsapp_api_key_encrypted)

    def set_marketing_whatsapp_api_key(self, value: str):
        self.marketing_whatsapp_api_key_encrypted = self._encrypt_secret(value)


class Permission(models.Model):
    """Stable permission key stored in DB for M2M grant/revoke overrides."""
    key = models.CharField(max_length=80, unique=True, db_index=True)
    label = models.CharField(max_length=150)
    group = models.CharField(max_length=50)

    class Meta:
        ordering = ["group", "key"]

    def __str__(self):
        return f"{self.key} — {self.label}"


class BusinessSettings(models.Model):
    """Per-agency business configuration — contracts, insurance, billing, maintenance."""
    agency = models.OneToOneField(
        Agency, on_delete=models.CASCADE, related_name="business_settings",
    )

    # ── Widget 1: Contrats & kilométrage ──
    km_included = models.PositiveIntegerField(null=True, blank=True, default=200)
    KM_TYPE_CHOICES = [("per_day", "Par jour"), ("per_contract", "Par contrat")]
    km_type = models.CharField(max_length=20, choices=KM_TYPE_CHOICES, default="per_day", blank=True)
    km_unlimited = models.BooleanField(default=False)
    km_extra_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, default=0.30)
    late_tolerance_minutes = models.PositiveIntegerField(null=True, blank=True, default=30)
    LATE_BILLING_CHOICES = [("prorata", "Prorata"), ("full_day", "Journée entière")]
    late_billing_mode = models.CharField(max_length=20, choices=LATE_BILLING_CHOICES, default="prorata", blank=True)
    late_fee_per_day = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, default=50.00)
    FUEL_POLICY_CHOICES = [
        ("full_full", "Plein → Plein"),
        ("full_empty", "Plein → Vide"),
        ("free", "Libre"),
    ]
    fuel_policy = models.CharField(max_length=20, choices=FUEL_POLICY_CHOICES, default="full_full", blank=True)
    fuel_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, default=30.00)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0.00)
    CURRENCY_CHOICES = [
        ("EUR", "EUR — Euro"),
        ("USD", "USD — Dollar US"),
        ("MAD", "MAD — Dirham"),
        ("XOF", "XOF — Franc CFA"),
        ("GBP", "GBP — Livre sterling"),
        ("CAD", "CAD — Dollar canadien"),
        ("CHF", "CHF — Franc suisse"),
        ("TND", "TND — Dinar tunisien"),
        ("DZD", "DZD — Dinar algérien"),
    ]
    currency = models.CharField(max_length=5, choices=CURRENCY_CHOICES, default="EUR", blank=True)
    ROUNDING_CHOICES = [("0.01", "0.01"), ("0.05", "0.05"), ("1", "1")]
    invoice_rounding = models.CharField(max_length=5, choices=ROUNDING_CHOICES, default="0.01", blank=True)

    # ── Widget 2: Assurance & dépôt ──
    deposit_default = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=500.00)
    DEPOSIT_MODE_CHOICES = [
        ("card_hold", "Empreinte carte"),
        ("cash", "Espèce"),
        ("transfer", "Virement"),
    ]
    deposit_mode = models.CharField(max_length=20, choices=DEPOSIT_MODE_CHOICES, default="cash", blank=True)
    insurance_franchise = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0.00)
    insurance_included = models.BooleanField(default=False)
    franchise_buyback = models.BooleanField(default=False)
    franchise_buyback_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, default=0.00)

    # ── Widget 3: Paiements & facturation ──
    auto_number_contracts = models.BooleanField(default=True)
    auto_number_invoices = models.BooleanField(default=True)
    contract_prefix = models.CharField(max_length=20, blank=True, default="CTR-")
    invoice_prefix = models.CharField(max_length=20, blank=True, default="FAC-")
    pay_cash = models.BooleanField(default=True)
    pay_card = models.BooleanField(default=True)
    pay_transfer = models.BooleanField(default=False)
    pay_mobile_money = models.BooleanField(default=False)
    partial_payment_allowed = models.BooleanField(default=False)
    invoice_due_days = models.PositiveIntegerField(null=True, blank=True, default=30)

    # ── Widget 5: Négociation prix ──
    allow_price_negotiation = models.BooleanField(default=False)
    negotiation_min_percent = models.PositiveSmallIntegerField(default=70)

    # ── Widget 6: Clauses contrat ──
    default_contract_clause = models.TextField(
        blank=True, default="Le locataire reconnaît avoir reçu le véhicule en bon état de fonctionnement "
        "à la date et heure indiquées ci-dessus. Il s'engage à le restituer dans le même état, "
        "à la date et heure convenues. Tout retard de restitution entraînera des pénalités "
        "conformément aux conditions tarifaires de l'agence. Le locataire est responsable de tout "
        "dommage causé au véhicule pendant la durée de la location.",
    )
    default_penalty_clause = models.TextField(
        blank=True, default="En cas de retard de restitution, une pénalité sera appliquée par jour de retard. "
        "En cas de dommage constaté au retour, les frais de réparation seront à la charge du locataire, "
        "déduction faite de la franchise d'assurance le cas échéant.",
    )

    # ── Widget 7: GPS & Géolocalisation ──
    gps_tracking_enabled = models.BooleanField(default=False, help_text="Activer le suivi GPS pour l'agence")
    gps_speed_limit = models.PositiveIntegerField(null=True, blank=True, default=130, help_text="Limite de vitesse (km/h)")
    gps_offline_alert_minutes = models.PositiveIntegerField(null=True, blank=True, default=30, help_text="Alerte si GPS hors ligne (minutes)")
    default_gps_clause = models.TextField(
        blank=True,
        default="Le véhicule est équipé d'un système de géolocalisation GPS. Le locataire est informé "
        "que la position du véhicule peut être suivie pendant toute la durée du contrat à des fins "
        "de sécurité et de gestion de flotte. Le locataire s'engage à ne pas désactiver, endommager "
        "ou interférer avec le dispositif GPS. Toute entrée dans une zone géographique interdite "
        "définie par l'agence déclenchera une alerte et pourra entraîner des pénalités.",
    )

    # ── Widget 4: Maintenance & alertes ──
    maintenance_interval_km = models.PositiveIntegerField(null=True, blank=True, default=10000)
    maintenance_interval_months = models.PositiveIntegerField(null=True, blank=True, default=6)
    maintenance_alert_km = models.PositiveIntegerField(null=True, blank=True, default=500)
    maintenance_alert_days = models.PositiveIntegerField(null=True, blank=True, default=15)
    maintenance_grace_km = models.PositiveIntegerField(null=True, blank=True, default=300)
    maintenance_email_alert = models.BooleanField(default=False)
    maintenance_disable_vehicle = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Business Settings"
        verbose_name_plural = "Business Settings"

    def __str__(self):
        return f"BusinessSettings — {self.agency}"


# ═══════════════════════════ THEME SETTINGS ══════════════════════════

class AgencyThemeSettings(models.Model):
    THEME_CHOICES = [
        ("dark", "Dark Luxury"),
        ("gaboom", "Gaboom Signature"),
    ]
    agency = models.OneToOneField(
        Agency, on_delete=models.CASCADE, related_name="theme_settings",
    )
    theme_choice = models.CharField(max_length=20, choices=THEME_CHOICES, default="dark")
    primary_color = models.CharField(max_length=20, blank=True, default="")
    secondary_color = models.CharField(max_length=20, blank=True, default="")
    border_radius = models.PositiveSmallIntegerField(default=14)
    enable_animations = models.BooleanField(default=True)
    enable_glow_effect = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Theme Settings"
        verbose_name_plural = "Theme Settings"

    def __str__(self):
        return f"ThemeSettings — {self.agency} ({self.theme_choice})"


class Vehicle(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="vehicles")
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    plate_number = models.CharField(max_length=50)
    daily_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default="available")
    public_visible = models.BooleanField(default=True)
    allow_negotiation = models.BooleanField(default=False)
    image = models.ImageField(upload_to="vehicles/", null=True, blank=True)
    current_km = models.PositiveIntegerField(default=0)
    last_maintenance_km = models.PositiveIntegerField(default=0)
    last_maintenance_date = models.DateField(null=True, blank=True)

    # ── GPS Tracking ──
    gps_imei = models.CharField(max_length=50, blank=True, default="", help_text="IMEI du boîtier GPS")
    gps_ip = models.GenericIPAddressField(null=True, blank=True, help_text="IP du tracker GPS")
    gps_enabled = models.BooleanField(default=False, help_text="Suivi GPS activé")
    gps_source = models.CharField(
        max_length=20, blank=True, default="device",
        choices=[("device", "Boîtier GPS"), ("phone", "Téléphone client")],
        help_text="Source du signal GPS",
    )
    last_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_gps_speed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    last_gps_update = models.DateTimeField(null=True, blank=True)

    objects = AgencyQuerySet.as_manager()

    def _bs(self):
        """Return agency BusinessSettings (cached)."""
        try:
            return self.agency.business_settings
        except BusinessSettings.DoesNotExist:
            return None

    @property
    def maintenance_interval(self):
        bs = self._bs()
        return bs.maintenance_interval_km if bs and bs.maintenance_interval_km else 10000

    @property
    def maintenance_alert_km(self):
        bs = self._bs()
        return bs.maintenance_alert_km if bs and bs.maintenance_alert_km else 500

    @property
    def maintenance_grace_km(self):
        bs = self._bs()
        return bs.maintenance_grace_km if bs and bs.maintenance_grace_km else 300

    @property
    def next_maintenance_km(self):
        return self.last_maintenance_km + self.maintenance_interval

    @property
    def km_remaining(self):
        return max(self.next_maintenance_km - self.current_km, 0)

    @property
    def needs_maintenance(self):
        return self.current_km >= self.next_maintenance_km

    @property
    def maintenance_soon(self):
        return (not self.needs_maintenance
                and self.current_km >= self.next_maintenance_km - self.maintenance_alert_km)

    @property
    def maintenance_status(self):
        """Return one of: 'blocked', 'urgent', 'soon', 'ok'.
        blocked = exceeded next_km + grace_km (or vehicle.status == maintenance)
        urgent  = exceeded next_km but within grace
        soon    = within alert_km of next_km
        ok      = everything fine
        """
        next_km = self.next_maintenance_km
        if self.status == "maintenance" or self.current_km >= next_km + self.maintenance_grace_km:
            return "blocked"
        if self.current_km >= next_km:
            return "urgent"
        if self.current_km >= next_km - self.maintenance_alert_km:
            return "soon"
        return "ok"

    @property
    def maintenance_blocked(self):
        return self.maintenance_status == "blocked"

    @property
    def maintenance_overflow_km(self):
        return max(self.current_km - self.next_maintenance_km, 0)

    @property
    def maintenance_progress_pct(self):
        """Percentage between last maintenance and next (0-100)."""
        interval = self.maintenance_interval
        if interval <= 0:
            return 100
        driven = self.current_km - self.last_maintenance_km
        return min(int(driven / interval * 100), 100)

    class Meta:
        ordering = ["make", "model", "plate_number"]

    def __str__(self) -> str:
        return f"{self.make} {self.model} ({self.plate_number})"


class MaintenanceRecord(models.Model):
    """Historical record of a maintenance intervention."""
    SERVICE_TYPE_CHOICES = [
        ("oil_change", "Vidange"),
        ("tires", "Pneus"),
        ("revision", "Révision générale"),
        ("brakes", "Freins"),
        ("battery", "Batterie"),
        ("filters", "Filtres"),
        ("timing_belt", "Courroie de distribution"),
        ("other", "Autre"),
    ]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="maintenance_records")
    date = models.DateField()
    km_at_service = models.PositiveIntegerField()
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPE_CHOICES, default="revision")
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.vehicle} — {self.get_service_type_display()} ({self.date})"


# ═══════════════════════════ GPS TRACKING ═════════════════════════════

class GPSDevice(models.Model):
    PROVIDER_CHOICES = [
        ("generic", "Generic"),
        ("brand_x", "Brand X"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="gps_devices")
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default="generic")
    imei = models.CharField(max_length=50)
    display_name = models.CharField(max_length=120, blank=True, default="")
    auth_token = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    linked_vehicle = models.OneToOneField(
        "Vehicle", on_delete=models.SET_NULL, null=True, blank=True, related_name="gps_device",
    )

    objects = AgencyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agency", "imei"], name="gps_device_unique_imei_agency"),
        ]

    def save(self, *args, **kwargs):
        if not self.auth_token:
            self.auth_token = secrets.token_urlsafe(32)[:64]
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.display_name or self.imei
        return f"{label} ({self.get_provider_display()})"

class GeoZone(models.Model):
    """Geographic zone (geofence) defined by the agency. Vehicles entering
    a 'restricted' zone trigger an alert."""
    ZONE_TYPE_CHOICES = [
        ("restricted", "Zone interdite"),
        ("allowed", "Zone autorisée"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="geo_zones")
    name = models.CharField(max_length=120)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPE_CHOICES, default="restricted")
    # Circle-based geofence (simple & efficient)
    center_lat = models.DecimalField(max_digits=10, decimal_places=7)
    center_lng = models.DecimalField(max_digits=10, decimal_places=7)
    radius_km = models.DecimalField(max_digits=7, decimal_places=2, default=5, help_text="Rayon en km")
    # Optional polygon (JSON array of [lat,lng] pairs) for complex shapes
    polygon_json = models.TextField(blank=True, default="", help_text="GeoJSON coordinates (optional)")
    is_active = models.BooleanField(default=True)
    alert_enabled = models.BooleanField(default=True)
    color = models.CharField(max_length=20, blank=True, default="#ef4444")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AgencyQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_zone_type_display()})"

    def contains_point(self, lat, lng):
        """Check if a lat/lng point is inside this zone (circle check)."""
        if self.polygon_json:
            try:
                data = json.loads(self.polygon_json)
                coords = None
                if isinstance(data, dict):
                    if "coordinates" in data:
                        coords = data.get("coordinates")
                    elif "geometry" in data and isinstance(data.get("geometry"), dict):
                        coords = data["geometry"].get("coordinates")
                elif isinstance(data, list):
                    coords = data
                if coords:
                    ring = coords[0] if isinstance(coords[0], list) and coords and isinstance(coords[0][0], (list, tuple)) else coords
                    poly = []
                    for pt in ring:
                        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                            continue
                        a, b = float(pt[0]), float(pt[1])
                        if abs(a) > 90 and abs(b) <= 90:
                            lng_pt, lat_pt = a, b
                        else:
                            lat_pt, lng_pt = a, b
                        poly.append((lat_pt, lng_pt))
                    if len(poly) >= 3:
                        x = float(lng)
                        y = float(lat)
                        inside = False
                        j = len(poly) - 1
                        for i in range(len(poly)):
                            yi, xi = poly[i]
                            yj, xj = poly[j]
                            intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
                            if intersect:
                                inside = not inside
                            j = i
                        return inside
            except Exception:
                pass
        from math import radians, cos, sin, asin, sqrt
        lat1, lon1 = radians(float(self.center_lat)), radians(float(self.center_lng))
        lat2, lon2 = radians(float(lat)), radians(float(lng))
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        km = 6371 * 2 * asin(sqrt(a))
        return km <= float(self.radius_km)


class VehicleZoneState(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="vehicle_zone_states")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="zone_states")
    zone = models.ForeignKey(GeoZone, on_delete=models.CASCADE, related_name="vehicle_states")
    is_inside = models.BooleanField(default=False)
    last_changed_at = models.DateTimeField(null=True, blank=True)
    last_violation_at = models.DateTimeField(null=True, blank=True)

    objects = AgencyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["vehicle", "zone"], name="vehicle_zone_state_unique"),
        ]

    def __str__(self):
        return f"{self.vehicle} — {self.zone} ({'inside' if self.is_inside else 'outside'})"


class GPSPositionLog(models.Model):
    """Historical GPS position log for a vehicle."""
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="gps_logs")
    lat = models.DecimalField(max_digits=10, decimal_places=7)
    lng = models.DecimalField(max_digits=10, decimal_places=7)
    speed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heading = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    source = models.CharField(max_length=20, default="device")
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["vehicle", "-recorded_at"]),
        ]

    def __str__(self):
        return f"{self.vehicle} @ {self.lat},{self.lng} ({self.recorded_at})"


class GeofenceEvent(models.Model):
    EVENT_CHOICES = [
        ("enter", "Entrée"),
        ("exit", "Sortie"),
        ("violation", "Violation"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="geofence_events")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="geofence_events")
    zone = models.ForeignKey(GeoZone, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    occurred_at = models.DateTimeField()
    lat = models.DecimalField(max_digits=10, decimal_places=7)
    lng = models.DecimalField(max_digits=10, decimal_places=7)
    payload = models.JSONField(null=True, blank=True)

    objects = AgencyQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.vehicle} — {self.zone} ({self.get_event_type_display()})"


class GPSAlert(models.Model):
    """Alert triggered when a vehicle enters a restricted zone."""
    ALERT_TYPE_CHOICES = [
        ("zone_enter", "Entrée zone interdite"),
        ("zone_exit", "Sortie zone autorisée"),
        ("zone_violation", "Violation zone interdite"),
        ("speed", "Excès de vitesse"),
        ("offline", "GPS hors ligne"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="gps_alerts")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="gps_alerts")
    zone = models.ForeignKey(GeoZone, on_delete=models.SET_NULL, null=True, blank=True, related_name="alerts")
    contract = models.ForeignKey(
        "billing.Contract", on_delete=models.SET_NULL, null=True, blank=True, related_name="gps_alerts",
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    message = models.TextField(blank=True, default="")
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AgencyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Alerte {self.get_alert_type_display()} — {self.vehicle} ({self.created_at})"


# ═══════════════════════════ SITE BUILDER ═════════════════════════════

class AgencySiteSettings(models.Model):
    """Per-agency website builder configuration."""
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("published", "Publié"),
    ]

    agency = models.OneToOneField(
        Agency, on_delete=models.CASCADE, related_name="site_settings",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    is_public_enabled = models.BooleanField(default=True)
    is_maintenance_enabled = models.BooleanField(default=False)

    # Theme
    theme_key = models.CharField(max_length=64, default="default")
    primary_color = models.CharField(max_length=16, default="#6D28D9")
    secondary_color = models.CharField(max_length=16, default="#FACC15")
    font_family = models.CharField(max_length=64, default="Inter")

    # Hero / content
    hero_title = models.CharField(max_length=120, blank=True, default="")
    hero_subtitle = models.CharField(max_length=180, blank=True, default="")
    cta_text = models.CharField(max_length=60, blank=True, default="Réserver")

    # Contact
    city = models.CharField(max_length=80, blank=True, default="")
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    whatsapp = models.CharField(max_length=30, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")

    # Logo
    logo = models.ImageField(upload_to="agencies/site_logos/", blank=True, null=True)

    # SEO
    seo_title = models.CharField(max_length=70, blank=True, default="")
    seo_description = models.CharField(max_length=160, blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Agency Site Settings"
        verbose_name_plural = "Agency Site Settings"

    def __str__(self):
        return f"SiteSettings — {self.agency}"

    def ensure_defaults(self):
        """Auto-fill empty fields from agency data."""
        if not self.hero_title:
            self.hero_title = self.agency.name
        if not self.contact_phone and self.agency.phone:
            self.contact_phone = self.agency.phone
        if not self.whatsapp and self.agency.whatsapp:
            self.whatsapp = self.agency.whatsapp
        if not self.contact_email and self.agency.contact_email:
            self.contact_email = self.agency.contact_email
        if not self.city and self.agency.city:
            self.city = self.agency.city
        if not self.primary_color:
            self.primary_color = self.agency.primary_color or "#6D28D9"
        if not self.secondary_color:
            self.secondary_color = self.agency.secondary_color or "#FACC15"


class AgencySiteSection(models.Model):
    """Toggleable sections for the public site home page."""
    PAGE_CHOICES = [("home", "Home")]

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="site_sections",
    )
    page = models.CharField(max_length=32, choices=PAGE_CHOICES, default="home")
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=80, default="")
    description = models.CharField(max_length=160, blank=True, default="")
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    content_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["agency", "page", "key"],
                name="uniq_agency_page_key",
            ),
        ]

    def __str__(self):
        return f"{self.agency} — {self.page}/{self.key}"


DEFAULT_HOME_SECTIONS = [
    {"key": "hero", "label": "Hero", "description": "Bannière principale avec titre et CTA", "order": 0},
    {"key": "featured_vehicles", "label": "Véhicules vedettes", "description": "Grille des véhicules publics", "order": 1},
    {"key": "benefits", "label": "Avantages", "description": "Points forts de votre agence", "order": 2},
    {"key": "process", "label": "Comment ça marche", "description": "Étapes de réservation", "order": 3},
    {"key": "contact_bar", "label": "Barre de contact", "description": "Téléphone, WhatsApp, email", "order": 4},
]


@receiver(post_save, sender=Agency)
def create_agency_site_defaults(sender, instance, created, **kwargs):
    """Auto-create AgencySiteSettings + default sections on new Agency."""
    if created:
        ss, _ = AgencySiteSettings.objects.get_or_create(agency=instance)
        ss.ensure_defaults()
        ss.save()
        for sec in DEFAULT_HOME_SECTIONS:
            AgencySiteSection.objects.get_or_create(
                agency=instance, page="home", key=sec["key"],
                defaults={
                    "label": sec["label"],
                    "description": sec["description"],
                    "order": sec["order"],
                },
            )


@receiver(post_save, sender=Agency)
def create_agency_access(sender, instance, created, **kwargs):
    """Auto-create AgencyAccess (trial 3 days) on new Agency."""
    if created:
        from agencies.services import get_agency_access
        get_agency_access(instance)


# ═══════════════════════════ RESERVATIONS ═════════════════════════════

class ReservationRequestQuerySet(models.QuerySet):
    def for_agency(self, agency):
        return self.filter(agency=agency)

    def confirmed(self):
        return self.filter(status="confirmed")

    def pending(self):
        return self.filter(status="pending")


def _make_public_secret(token, agency_id):
    """Generate a SHA-256 hash for secure public tracking links."""
    raw = f"{token}{settings.SECRET_KEY}{agency_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


def has_date_conflict(vehicle, start_date, end_date, exclude_pk=None):
    """Check if a confirmed reservation overlaps the given date range."""
    qs = ReservationRequest.objects.filter(
        vehicle=vehicle,
        status="confirmed",
    ).filter(
        ~Q(end_date__lt=start_date) & ~Q(start_date__gt=end_date)
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


class ReservationRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("confirmed", "Confirmée"),
        ("contracted", "Sous contrat"),
        ("rejected", "Refusée"),
        ("expired", "Expirée"),
    ]
    SOURCE_CHOICES = [
        ("public_site", "Site public"),
        ("dashboard", "Dashboard"),
        ("phone", "Téléphone"),
    ]

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="reservation_requests",
    )
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="reservation_requests",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Client info (no account required)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    whatsapp = models.CharField(max_length=30, blank=True, default="")

    # Optional link to portal client account
    client_account = models.ForeignKey(
        "clients.ClientAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )

    # Dates
    start_date = models.DateField()
    end_date = models.DateField()
    message = models.TextField(blank=True, default="")

    # Tracking
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    public_secret = models.CharField(max_length=64, editable=False, default="")
    client_seen_at = models.DateTimeField(null=True, blank=True)

    # Admin
    admin_note = models.TextField(blank=True, default="")
    decision_message = models.CharField(max_length=180, blank=True, default="")

    # Optional
    desired_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    source = models.CharField(max_length=40, choices=SOURCE_CHOICES, default="public_site")

    # ── Négociation prix ──
    NEGOTIATION_STATUS_CHOICES = [
        ("none", "Standard"),
        ("pending_offer", "Offre client"),
        ("countered", "Contre-offre"),
        ("accepted", "Accord"),
        ("refused", "Refusé"),
    ]
    daily_price_official = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    daily_price_offer = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    daily_price_counter = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    daily_price_accepted = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    negotiation_status = models.CharField(
        max_length=20, choices=NEGOTIATION_STATUS_CHOICES, default="none",
    )
    negotiation_message = models.TextField(blank=True, default="")
    agency_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReservationRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agency", "status", "created_at"]),
            models.Index(fields=["vehicle", "start_date", "end_date"]),
            models.Index(fields=["public_token"]),
        ]

    def __str__(self):
        return f"Réservation #{self.pk} — {self.full_name} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être après la date de début."})
        if self.vehicle_id and self.agency_id and self.vehicle.agency_id != self.agency_id:
            raise ValidationError({"vehicle": "Le véhicule n'appartient pas à cette agence."})

    def save(self, *args, **kwargs):
        if not self.public_secret:
            self.public_secret = _make_public_secret(self.public_token, self.agency_id)
        super().save(*args, **kwargs)

    def verify_secret(self, secret):
        return secret == self.public_secret

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    @property
    def daily_price_final(self):
        """Resolved daily price: accepted > counter (if accepted) > offer (if accepted) > official > vehicle price."""
        if self.daily_price_accepted:
            return self.daily_price_accepted
        if self.daily_price_official:
            return self.daily_price_official
        if self.vehicle:
            return self.vehicle.daily_price
        return 0

    @property
    def estimated_total(self):
        if self.duration_days:
            return self.daily_price_final * self.duration_days
        return 0


# ═══════════════════════════ PROMO CODES ══════════════════════════════

class PromoCode(models.Model):
    TYPE_CHOICES = [
        ("percent", "Pourcentage"),
        ("fixed", "Montant fixe"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="promo_codes")
    code = models.CharField(max_length=50)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="percent")
    value = models.DecimalField(max_digits=10, decimal_places=2)
    valid_until = models.DateField(null=True, blank=True)
    max_usage = models.PositiveIntegerField(default=0)
    usage_count = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("agency", "code")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.agency})"

    @property
    def is_valid(self):
        from datetime import date
        if not self.active:
            return False
        if self.valid_until and self.valid_until < date.today():
            return False
        if self.max_usage and self.usage_count >= self.max_usage:
            return False
        return True

    def apply_discount(self, price):
        """Return discounted price."""
        from decimal import Decimal
        if self.type == "percent":
            return (price * (100 - self.value) / 100).quantize(Decimal("0.01"))
        return max(price - self.value, Decimal("0"))


# ═══════════════════════════ SITE BANNERS ═════════════════════════════

class SiteBanner(models.Model):
    BANNER_TYPE_CHOICES = [
        ("hero", "Hero"),
        ("inline", "Inline"),
        ("popup", "Popup"),
        ("sidebar", "Sidebar"),
        ("countdown", "Countdown"),
    ]
    DEVICE_CHOICES = [
        ("all", "Tous"),
        ("mobile", "Mobile"),
        ("desktop", "Desktop"),
    ]
    ANIMATION_CHOICES = [
        ("fade", "Fade"),
        ("slide", "Slide"),
        ("zoom", "Zoom"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="site_banners")
    type = models.CharField(max_length=20, choices=BANNER_TYPE_CHOICES, default="hero")
    image = models.ImageField(upload_to="banners/", null=True, blank=True)
    title = models.CharField(max_length=200, blank=True, default="")
    subtitle = models.CharField(max_length=300, blank=True, default="")
    button_text = models.CharField(max_length=60, blank=True, default="")
    button_link = models.CharField(max_length=500, blank=True, default="")
    active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    target_device = models.CharField(max_length=10, choices=DEVICE_CHOICES, default="all")
    animation_type = models.CharField(max_length=10, choices=ANIMATION_CHOICES, default="fade")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.title or 'Sans titre'}"

    @property
    def is_active_now(self):
        from datetime import date
        today = date.today()
        if not self.active:
            return False
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        return True


# ═══════════════════════════ MARKETING CAMPAIGNS ═════════════════════

class MarketingCampaign(models.Model):
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("scheduled", "Planifiée"),
        ("sent", "Envoyée"),
    ]
    TARGET_CHOICES = [
        ("all", "Tous les clients"),
        ("inactive", "Clients inactifs"),
        ("frequent", "Clients fréquents"),
        ("negotiators", "Négociateurs"),
    ]
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="campaigns")
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES, default="all")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)
    channel_config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class CampaignLog(models.Model):
    STATUS_CHOICES = [
        ("sent", "Envoyé"),
        ("failed", "Échoué"),
    ]
    campaign = models.ForeignKey(MarketingCampaign, on_delete=models.CASCADE, related_name="logs")
    client = models.ForeignKey(
        "clients.ClientAccount", on_delete=models.CASCADE, related_name="campaign_logs",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="sent")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]


# ═══════════════════════════ CAMPAIGN AUTOMATION ═══════════════════════

class CampaignAutomation(models.Model):
    TRIGGER_CHOICES = [
        ("manual", "Manuel (ponctuel)"),
        ("new_client", "Nouveau client"),
        ("pending_reservation", "Réservation en attente"),
        ("contract_ended", "Contrat terminé"),
        ("inactive_client", "Client inactif"),
    ]
    campaign = models.OneToOneField(
        MarketingCampaign, on_delete=models.CASCADE, related_name="automation",
    )
    enabled = models.BooleanField(default=False)
    is_sequence = models.BooleanField(default=False)
    trigger = models.CharField(max_length=30, choices=TRIGGER_CHOICES, default="manual")
    stop_conditions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Campaign Automation"

    def __str__(self):
        return f"Automation — {self.campaign.title}"


class CampaignStep(models.Model):
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ]
    automation = models.ForeignKey(
        CampaignAutomation, on_delete=models.CASCADE, related_name="steps",
    )
    order = models.PositiveSmallIntegerField(default=0)
    day_offset = models.PositiveSmallIntegerField(default=0)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="email")
    content = models.TextField(blank=True, default="")
    send_time = models.TimeField(default="09:00")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Step {self.order} — J+{self.day_offset} ({self.channel})"


class OutboundMessage(models.Model):
    STATUS_CHOICES = [
        ("queued", "En file"),
        ("sent", "Envoyé"),
        ("failed", "Échoué"),
    ]
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ]
    campaign = models.ForeignKey(
        MarketingCampaign, on_delete=models.CASCADE, related_name="outbound_messages",
    )
    step = models.ForeignKey(
        CampaignStep, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="outbound_messages",
    )
    client = models.ForeignKey(
        "clients.ClientAccount", on_delete=models.CASCADE,
        related_name="outbound_messages",
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="email")
    content = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    wa_link = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} → {self.client} ({self.get_status_display()})"


# ═══════════════════════════ ACCESS / SUBSCRIPTION ════════════════════
from agencies.models_access import AgencyAccess, PaymentProof  # noqa: E402, F401
