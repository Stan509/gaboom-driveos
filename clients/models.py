from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from agencies.models import AgencyQuerySet


class Client(models.Model):
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("vip", "VIP"),
        ("blacklisted", "Blacklisté"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="clients",
    )
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    whatsapp = models.CharField(max_length=30, blank=True, default="")
    address = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    tags = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    # Driving license
    driving_license_number = models.CharField(max_length=100, blank=True, default="")
    driving_license_expiry = models.DateField(null=True, blank=True)

    # ID document upload
    id_document = models.ImageField(upload_to="clients/id/", null=True, blank=True)

    follow_up_at = models.DateField(null=True, blank=True)
    follow_up_note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    objects = AgencyQuerySet.as_manager()

    @property
    def license_expired(self):
        if not self.driving_license_expiry:
            return False
        return self.driving_license_expiry < timezone.now().date()

    @property
    def license_status(self):
        if not self.driving_license_expiry:
            return "missing"
        if self.license_expired:
            return "expired"
        return "valid"

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


# ═══════════════════════════ CLIENT PORTAL ACCOUNT ════════════════════

class ClientAccountQuerySet(models.QuerySet):
    def for_agency(self, agency):
        return self.filter(agency=agency)


class ClientAccount(models.Model):
    """Self-service portal account for end-clients. Separate from Django User."""

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="client_accounts",
    )
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True, default="")
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    # Optional link to the agency-managed Client record
    client_record = models.OneToOneField(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portal_account",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClientAccountQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("agency", "email")]
        verbose_name = "Compte client"
        verbose_name_plural = "Comptes clients"

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class ClientNotification(models.Model):
    TYPE_CHOICES = [
        ("info", "Info"),
        ("success", "Succès"),
        ("warn", "Attention"),
    ]

    client = models.ForeignKey(
        ClientAccount,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notif_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="info")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification client"
        verbose_name_plural = "Notifications clients"

    def __str__(self):
        return f"{self.title} → {self.client.full_name}"


# ═══════════════════════════ NEGOTIATION MESSAGES ═════════════════════

class NegotiationMessage(models.Model):
    """Internal chat messages between client and agency for a reservation negotiation."""
    SENDER_CHOICES = [
        ("client", "Client"),
        ("agency", "Agence"),
    ]

    reservation = models.ForeignKey(
        "agencies.ReservationRequest",
        on_delete=models.CASCADE,
        related_name="negotiation_messages",
    )
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    body = models.TextField(max_length=1000)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Message de négociation"
        verbose_name_plural = "Messages de négociation"

    def __str__(self):
        return f"[{self.get_sender_display()}] {self.body[:50]}"


# ═══════════════════════════ LOYALTY PROGRAM ══════════════════════════

class ClientLoyalty(models.Model):
    RANK_CHOICES = [
        ("bronze", "Bronze"),
        ("silver", "Silver"),
        ("gold", "Gold"),
        ("platinum", "Platinum"),
    ]
    client = models.OneToOneField(
        ClientAccount, on_delete=models.CASCADE, related_name="loyalty",
    )
    points = models.PositiveIntegerField(default=0)
    lifetime_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rank = models.CharField(max_length=10, choices=RANK_CHOICES, default="bronze")

    class Meta:
        verbose_name = "Fidélité client"
        verbose_name_plural = "Fidélités clients"

    def __str__(self):
        return f"{self.client.full_name} — {self.get_rank_display()} ({self.points} pts)"

    def recompute_rank(self):
        if self.points >= 1000:
            self.rank = "platinum"
        elif self.points >= 500:
            self.rank = "gold"
        elif self.points >= 200:
            self.rank = "silver"
        else:
            self.rank = "bronze"

    def add_revenue(self, amount):
        """Add revenue: 1$ = 1 point. Recompute rank."""
        from decimal import Decimal
        pts = int(amount)
        self.points += pts
        self.lifetime_value += Decimal(str(amount))
        self.recompute_rank()
        self.save(update_fields=["points", "lifetime_value", "rank"])

    @property
    def credit_available(self):
        """100 points = 10$ credit."""
        return (self.points // 100) * 10
