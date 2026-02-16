from django.db import models


class PayPalSubscription(models.Model):
    """
    Detailed tracking of a PayPal subscription per agency.
    One-to-one with AgencyAccess.
    """

    STATUS_CHOICES = [
        ("APPROVAL_PENDING", "En attente d'approbation"),
        ("APPROVED", "Approuvé"),
        ("ACTIVE", "Actif"),
        ("SUSPENDED", "Suspendu"),
        ("CANCELLED", "Annulé"),
        ("EXPIRED", "Expiré"),
    ]

    access = models.OneToOneField(
        "agencies.AgencyAccess",
        on_delete=models.CASCADE,
        related_name="paypal_sub",
    )
    paypal_subscription_id = models.CharField(
        max_length=120, unique=True, db_index=True,
        help_text="PayPal subscription ID (e.g. I-XXXXXXXXXX)",
    )
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="APPROVAL_PENDING",
    )
    plan_id = models.CharField(max_length=128, blank=True, default="")
    product_id = models.CharField(max_length=128, blank=True, default="")
    payer_email = models.EmailField(blank=True, default="")
    last_event_at = models.DateTimeField(null=True, blank=True)
    next_billing_time = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "PayPal Subscription"
        verbose_name_plural = "PayPal Subscriptions"

    def __str__(self):
        return f"{self.paypal_subscription_id} — {self.get_status_display()}"
