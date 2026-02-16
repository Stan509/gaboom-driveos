from django.db import models


class PayPalEvent(models.Model):
    """Stores raw PayPal webhook events for audit/debugging."""

    event_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=120, db_index=True)
    resource_id = models.CharField(
        max_length=120, blank=True, default="",
        help_text="subscription_id or payment_id from the resource",
    )
    subscription_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    agency_name = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=True)
    verified = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "PayPal Event"
        verbose_name_plural = "PayPal Events"

    def __str__(self):
        return f"{self.event_type} · {self.subscription_id} · {self.created_at:%d/%m/%Y %H:%M}"
