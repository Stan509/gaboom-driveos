from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AgencyAccess(models.Model):
    STATUS_CHOICES = [
        ("trial", "Essai gratuit"),
        ("active", "Actif"),
        ("suspended", "Suspendu"),
    ]

    BILLING_MODE_CHOICES = [
        ("manual", "Manuel"),
        ("paypal", "PayPal"),
    ]

    PAYPAL_STATUS_CHOICES = [
        ("none", "Aucun"),
        ("active", "Actif"),
        ("cancelled", "Annulé"),
        ("suspended", "Suspendu"),
        ("expired", "Expiré"),
    ]

    PLAN_CHOICES = [
        ("starter", "Starter"),
        ("business", "Business"),
        ("enterprise", "Enterprise"),
    ]

    ADMIN_ALERT_CHOICES = [
        ("none", "Aucune"),
        ("paypal_cancelled", "PayPal annulé"),
        ("paypal_payment_failed", "Paiement PayPal échoué"),
        ("paypal_status_unknown", "Statut PayPal inconnu"),
        ("paypal_to_manual", "PayPal → Manuel"),
        ("manual_to_paypal", "Manuel → PayPal"),
    ]

    agency = models.OneToOneField(
        "agencies.Agency", on_delete=models.CASCADE, related_name="access",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="trial")

    trial_started_at = models.DateTimeField(default=timezone.now)
    access_ends_at = models.DateTimeField(
        help_text="Date limite actuelle (fin trial ou fin active).",
        default=timezone.now,
    )
    suspended_reason = models.TextField(blank=True, default="")
    notes_internal = models.TextField(blank=True, default="")

    plan_code = models.CharField(
        max_length=20, choices=PLAN_CHOICES, default="starter",
    )
    plan_name = models.CharField(max_length=40, default="Starter")
    plan_price = models.DecimalField(max_digits=8, decimal_places=2, default=59)
    plan_currency = models.CharField(max_length=3, default="USD")
    max_agencies = models.PositiveIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=3)
    max_vehicles = models.PositiveIntegerField(default=20)
    plan_features = models.JSONField(default=dict, blank=True)

    # ── Billing mode ──
    billing_mode = models.CharField(
        max_length=20, choices=BILLING_MODE_CHOICES, default="manual",
    )

    # ── PayPal fields ──
    paypal_subscription_id = models.CharField(
        max_length=120, blank=True, default="",
        help_text="ID d'abonnement PayPal (ex: I-XXXXXXXXXX).",
    )
    paypal_status = models.CharField(
        max_length=20, choices=PAYPAL_STATUS_CHOICES, default="none",
    )
    paypal_last_event_at = models.DateTimeField(null=True, blank=True)
    paypal_cancelled_at = models.DateTimeField(null=True, blank=True)

    # ── Billing tracking ──
    billing_last_changed_at = models.DateTimeField(auto_now=True)
    billing_last_changed_reason = models.TextField(blank=True, default="")

    # ── Admin alerts ──
    needs_admin_attention = models.BooleanField(default=False)
    admin_alert_code = models.CharField(
        max_length=30, choices=ADMIN_ALERT_CHOICES, default="none",
    )
    admin_alert_message = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Agency Access"
        verbose_name_plural = "Agency Accesses"

    def __str__(self):
        return f"{self.agency} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.access_ends_at:
            self.access_ends_at = self.trial_started_at + timedelta(days=3)
        super().save(*args, **kwargs)

    # ── Computed helpers ──

    @property
    def is_paypal(self):
        return self.billing_mode == "paypal"

    @property
    def is_manual(self):
        return self.billing_mode == "manual"

    @property
    def access_source_label(self):
        return "PayPal Auto" if self.is_paypal else "Manuel"

    @property
    def is_active_now(self):
        """True if agency currently has valid access."""
        if self.status == "suspended":
            return False
        return timezone.now() < self.access_ends_at

    @property
    def is_expired(self):
        """True if deadline has passed (regardless of status field)."""
        return timezone.now() >= self.access_ends_at

    @property
    def should_block_now(self):
        """Determine if agency should be blocked right now."""
        if self.status == "suspended":
            return True
        if self.billing_mode == "paypal":
            if self.paypal_status == "active":
                return False
            return self.is_expired
        return self.is_expired

    @property
    def days_remaining(self):
        remaining = self.access_ends_at - timezone.now()
        if remaining.total_seconds() < 0:
            return 0
        return max(0, remaining.days)

    @property
    def countdown_label(self):
        if self.status == "suspended":
            return "Suspendu"
        if self.is_paypal and self.paypal_status == "active":
            return "PayPal actif"
        remaining = self.access_ends_at - timezone.now()
        total_seconds = remaining.total_seconds()
        if total_seconds <= 0:
            return "Expiré"
        days = int(total_seconds // 86400)
        hours = int((total_seconds % 86400) // 3600)
        if days > 1:
            return f"{days} jours restants"
        elif days == 1:
            return f"1 jour et {hours}h restants"
        elif hours > 0:
            minutes = int((total_seconds % 3600) // 60)
            return f"{hours}h {minutes}min restants"
        else:
            minutes = int(total_seconds // 60)
            return f"{minutes} min restantes"

    def plan_has_feature(self, key):
        return bool(self.plan_features.get(key))

    @property
    def users_unlimited(self):
        return self.max_users == 0

    @property
    def vehicles_unlimited(self):
        return self.max_vehicles == 0

    @property
    def agencies_unlimited(self):
        return self.max_agencies == 0


def _validate_proof_image(value):
    """Validate proof image: max 5MB, jpg/png/webp only."""
    max_size = 5 * 1024 * 1024
    if value.size > max_size:
        raise ValidationError("Fichier trop volumineux (max 5 Mo).")
    allowed = ("image/jpeg", "image/png", "image/webp")
    ct = getattr(value, "content_type", None) or ""
    if ct not in allowed:
        raise ValidationError("Format non supporté. Utilisez JPG, PNG ou WebP.")


class PaymentProof(models.Model):
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("approved", "Approuvée"),
        ("rejected", "Rejetée"),
    ]

    access = models.ForeignKey(
        AgencyAccess, on_delete=models.CASCADE, related_name="proofs",
    )
    image = models.ImageField(
        upload_to="payments/proofs/%Y/%m/",
        validators=[_validate_proof_image],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="submitted_proofs",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviewed_proofs",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Preuve #{self.pk} — {self.access.agency} ({self.get_status_display()})"

    @property
    def agency(self):
        return self.access.agency
