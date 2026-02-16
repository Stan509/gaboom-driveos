from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("ACCESS_RENEW", "Renouvellement accès"),
        ("ACCESS_SUSPEND", "Suspension accès"),
        ("ACCESS_BONUS", "Bonus jours"),
        ("PROOF_APPROVE", "Preuve approuvée"),
        ("PROOF_REJECT", "Preuve rejetée"),
        ("NOTES_UPDATE", "Notes mises à jour"),
        ("SETTINGS_UPDATE", "Paramètres modifiés"),
        ("ALERT_DISMISS", "Alerte traitée"),
        ("PAYPAL_SWITCH", "Changement mode paiement"),
    ]

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    proof = models.ForeignKey(
        "agencies.PaymentProof", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        agency_name = self.agency.name if self.agency else "—"
        return f"{self.get_action_display()} · {agency_name} · {self.created_at:%d/%m/%Y %H:%M}"
