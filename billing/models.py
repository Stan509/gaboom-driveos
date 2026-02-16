from decimal import Decimal

from django.conf import settings
from django.db import models

from agencies.models import AgencyQuerySet


class Contract(models.Model):
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("pending_signature", "En attente de signature"),
        ("active", "Actif"),
        ("pending_return", "Retour en cours"),
        ("closed", "Clôturé"),
        ("cancelled", "Annulé"),
    ]
    PAYMENT_STATUS_CHOICES = [
        ("unpaid", "Impayé"),
        ("partial", "Partiel"),
        ("paid", "Payé"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.CASCADE, related_name="contracts"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, related_name="contracts"
    )
    client_account = models.ForeignKey(
        "clients.ClientAccount", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="contracts",
    )
    vehicle = models.ForeignKey(
        "agencies.Vehicle", on_delete=models.PROTECT, related_name="contracts"
    )
    reservation = models.OneToOneField(
        "agencies.ReservationRequest", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="contract",
    )

    start_date = models.DateField()
    end_date = models.DateField()
    pickup_datetime = models.DateTimeField(null=True, blank=True)
    return_datetime = models.DateTimeField(null=True, blank=True)
    actual_return_datetime = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Km / fuel tracking
    km_depart = models.PositiveIntegerField(default=0)
    km_retour = models.PositiveIntegerField(null=True, blank=True)
    fuel_depart = models.PositiveSmallIntegerField(default=8, help_text="1-8 gauge")
    fuel_retour = models.PositiveSmallIntegerField(null=True, blank=True)

    # Contract-level overrides (pre-filled from Agency defaults)
    km_included = models.PositiveIntegerField(default=200)
    km_price = models.DecimalField(max_digits=6, decimal_places=2, default=0.30)
    fuel_fee = models.DecimalField(max_digits=8, decimal_places=2, default=30.00)
    late_fee = models.DecimalField(max_digits=8, decimal_places=2, default=50.00)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=5, default="EUR")

    # Computed fees (set on close)
    frais_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frais_carburant = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frais_degats = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frais_retard = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Totals
    subtotal_ht = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_tva = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="unpaid"
    )

    notes = models.TextField(blank=True, default="")

    # ── Contract clause (pre-filled from agency default, editable per contract) ──
    contract_clause = models.TextField(blank=True, default="")
    penalty_clause = models.TextField(blank=True, default="")
    gps_clause = models.TextField(blank=True, default="", help_text="Clause GPS ajoutée au contrat si le véhicule est suivi")

    # ── GPS consent (client accepts GPS tracking from their phone) ──
    gps_consent_signed_at = models.DateTimeField(null=True, blank=True)
    gps_consent_ip = models.GenericIPAddressField(null=True, blank=True)

    # ── Client signature ──
    client_signature = models.ImageField(
        upload_to="contracts/signatures/", null=True, blank=True,
    )
    client_signed_at = models.DateTimeField(null=True, blank=True)
    client_signed_ip = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = AgencyQuerySet.as_manager()

    # Statuses that mean the vehicle is "occupied" by this contract
    ACTIVE_STATUSES = ("draft", "pending_signature", "active", "pending_return")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Contrat #{self.pk} — {self.client}"

    @classmethod
    def vehicle_has_active_contract(cls, vehicle, exclude_pk=None):
        """Return the active contract for this vehicle, or None."""
        qs = cls.objects.filter(vehicle=vehicle, status__in=cls.ACTIVE_STATUSES)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        return qs.first()

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.vehicle_id:
            existing = Contract.vehicle_has_active_contract(
                self.vehicle, exclude_pk=self.pk,
            )
            if existing:
                raise ValidationError({
                    "vehicle": f"Ce véhicule est déjà lié au contrat #{existing.pk} "
                               f"(statut : {existing.get_status_display()}). "
                               f"Clôturez ou annulez ce contrat avant d'en créer un nouveau.",
                })

    @property
    def nb_days(self):
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days
            return max(delta, 1)
        return 0

    def compute_close(self, date_retour=None):
        """Compute all fees and totals for closing the contract."""
        from django.utils import timezone

        date_retour = date_retour or timezone.now().date()

        # Km surplus
        km_done = (self.km_retour or 0) - self.km_depart
        km_surplus = max(km_done - self.km_included, 0)
        self.frais_km = Decimal(km_surplus) * self.km_price

        # Fuel fee
        if self.fuel_retour is not None and self.fuel_retour < self.fuel_depart:
            self.frais_carburant = self.fuel_fee
        else:
            self.frais_carburant = Decimal(0)

        # Late fee
        if date_retour > self.end_date:
            late_days = (date_retour - self.end_date).days
            self.frais_retard = self.late_fee * late_days
        else:
            self.frais_retard = Decimal(0)

        # Subtotal HT = (days * price) + fees
        base = Decimal(self.nb_days) * self.price_per_day
        self.subtotal_ht = (
            base + self.frais_km + self.frais_carburant
            + self.frais_degats + self.frais_retard
        )

        # TVA
        if self.vat_percent > 0:
            self.montant_tva = (self.subtotal_ht * self.vat_percent / Decimal(100)).quantize(Decimal("0.01"))
        else:
            self.montant_tva = Decimal(0)

        self.montant_ttc = self.subtotal_ht + self.montant_tva
        self.amount_due = max(self.montant_ttc - self.amount_paid, Decimal(0))
        self._update_payment_status()

        self.status = "closed"
        self.closed_at = timezone.now()

    def _update_payment_status(self):
        if self.amount_paid >= self.montant_ttc and self.montant_ttc > 0:
            self.payment_status = "paid"
        elif self.amount_paid > 0:
            self.payment_status = "partial"
        else:
            self.payment_status = "unpaid"

    def recalc_payments(self):
        """Recalculate amount_paid from related payments."""
        total = self.payments.filter(status="succeeded").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal(0)
        self.amount_paid = total
        self.amount_due = max(self.montant_ttc - self.amount_paid, Decimal(0))
        self._update_payment_status()

    @property
    def is_signed(self):
        return self.client_signed_at is not None

    @property
    def can_sign(self):
        return self.status == "pending_signature" and not self.is_signed


class VehicleStatePhoto(models.Model):
    """Photos of vehicle condition at pickup or return."""
    MOMENT_CHOICES = [
        ("pickup", "Départ"),
        ("return", "Retour"),
    ]
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="vehicle_photos",
    )
    moment = models.CharField(max_length=10, choices=MOMENT_CHOICES)
    photo = models.ImageField(upload_to="contracts/vehicle_state/")
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["moment", "created_at"]

    def __str__(self):
        return f"{self.get_moment_display()} — Contrat #{self.contract_id}"


class VehicleReturnInspection(models.Model):
    """Inspection report when vehicle is returned."""
    CONDITION_CHOICES = [
        ("excellent", "Excellent"),
        ("good", "Bon"),
        ("fair", "Acceptable"),
        ("damaged", "Endommagé"),
    ]
    DECISION_CHOICES = [
        ("available", "Disponible immédiatement"),
        ("maintenance", "Envoyer en maintenance"),
    ]

    contract = models.OneToOneField(
        Contract, on_delete=models.CASCADE, related_name="return_inspection",
    )
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    inspected_at = models.DateTimeField(auto_now_add=True)

    # Condition ratings
    exterior_condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="good",
    )
    interior_condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="good",
    )
    tires_condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="good",
    )
    lights_condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="good",
    )
    engine_condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="good",
    )

    # Damage
    has_new_damage = models.BooleanField(default=False)
    damage_description = models.TextField(blank=True, default="")
    damage_cost_estimate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
    )

    # Cleanliness
    cleanliness_ok = models.BooleanField(default=True)

    # General notes
    notes = models.TextField(blank=True, default="")

    # Decision
    decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, default="available",
    )

    class Meta:
        verbose_name = "Inspection retour"

    def __str__(self):
        return f"Inspection — Contrat #{self.contract_id}"


class Payment(models.Model):
    METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("card_terminal", "Terminal CB"),
        ("bank_transfer", "Virement"),
    ]
    STATUS_CHOICES = [
        ("succeeded", "Réussi"),
        ("refunded", "Remboursé"),
        ("failed", "Échoué"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.CASCADE, related_name="payments"
    )
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=5, default="EUR")
    provider = models.CharField(max_length=20, default="manual")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="cash")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="succeeded")
    reference = models.CharField(max_length=100, blank=True, default="")
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AgencyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Paiement {self.amount}{self.currency} — Contrat #{self.contract_id}"
