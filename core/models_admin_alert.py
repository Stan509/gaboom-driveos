from django.db import models


class AdminAlert(models.Model):
    """
    Dedicated alert table for superadmin notifications.
    Created when PayPal events require attention, mode switches happen, etc.
    """

    TYPE_CHOICES = [
        ("paypal_cancelled", "PayPal annulé"),
        ("paypal_failed", "Paiement PayPal échoué"),
        ("paypal_suspended", "PayPal suspendu"),
        ("paypal_expired", "PayPal expiré"),
        ("mode_downgrade", "Passage PayPal → Manuel"),
        ("mode_upgrade", "Passage Manuel → PayPal"),
        ("manual_proof_pending", "Preuve manuelle en attente"),
        ("unknown_event", "Événement inconnu"),
        ("email_failed", "Email échoué"),
    ]

    alert_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="admin_alerts",
        null=True, blank=True,
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Admin Alert"
        verbose_name_plural = "Admin Alerts"

    def __str__(self):
        return f"[{self.alert_type}] {self.message[:60]}"
