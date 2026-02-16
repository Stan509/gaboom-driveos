"""
Marketing Engine 2.0 — Models
All campaign, variant, send tracking, automation, template, and bandit models.
"""
import uuid

from django.db import models
from django.utils import timezone

from agencies.models import Agency


# ═══════════════════════════ CAMPAIGN ═════════════════════════════════

class MktCampaign(models.Model):
    OBJECTIVE_CHOICES = [
        ("promo", "Promotion"),
        ("relance", "Relance"),
        ("fidelisation", "Fidélisation"),
        ("avis", "Avis client"),
        ("lancement", "Lancement"),
    ]
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("scheduled", "Planifiée"),
        ("running", "En cours"),
        ("done", "Terminée"),
    ]
    TARGET_CHOICES = [
        ("all_clients", "Tous les clients"),
        ("active_clients", "Clients actifs"),
        ("inactive_30d", "Inactifs 30 jours"),
        ("custom_tag", "Tag personnalisé"),
    ]

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="mkt_campaigns")
    name = models.CharField(max_length=200)
    objective = models.CharField(max_length=20, choices=OBJECTIVE_CHOICES, default="promo")
    channel_email = models.BooleanField(default=True)
    channel_whatsapp = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    target = models.CharField(max_length=30, choices=TARGET_CHOICES, default="all_clients")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    ab_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


# ═══════════════════════════ VARIANT (A/B) ════════════════════════════

class CampaignVariant(models.Model):
    STYLE_CHOICES = [
        ("simple", "Simple"),
        ("corporate", "Corporate"),
        ("urgent", "Urgent"),
        ("luxe", "Luxe"),
        ("ultra_premium", "Ultra Premium"),
    ]

    campaign = models.ForeignKey(MktCampaign, on_delete=models.CASCADE, related_name="variants")
    variant = models.CharField(max_length=5, default="A")
    subject = models.CharField(max_length=200, blank=True, default="")
    body_text = models.TextField(default="")
    style = models.CharField(max_length=20, choices=STYLE_CHOICES, default="simple")
    score = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["variant"]
        unique_together = [("campaign", "variant")]

    def __str__(self):
        return f"{self.campaign.name} — Variante {self.variant}"


# ═══════════════════════════ SEND TRACKING ════════════════════════════

class CampaignSend(models.Model):
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ]

    campaign = models.ForeignKey(MktCampaign, on_delete=models.CASCADE, related_name="sends")
    variant = models.ForeignKey(CampaignVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="sends")
    client = models.ForeignKey("clients.ClientAccount", on_delete=models.CASCADE, related_name="mkt_sends")
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="email")
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    sent_at = models.DateTimeField(default=timezone.now)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Send {self.token} → {self.client}"


# ═══════════════════════════ TEMPLATES ════════════════════════════════

class MarketingTemplate(models.Model):
    OBJECTIVE_CHOICES = MktCampaign.OBJECTIVE_CHOICES
    STYLE_CHOICES = CampaignVariant.STYLE_CHOICES
    CHANNEL_CHOICES = CampaignSend.CHANNEL_CHOICES

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, null=True, blank=True,
        related_name="mkt_templates",
    )
    key = models.CharField(max_length=80, db_index=True)
    name = models.CharField(max_length=120, default="")
    objective = models.CharField(max_length=20, choices=OBJECTIVE_CHOICES, default="promo")
    style = models.CharField(max_length=20, choices=STYLE_CHOICES, default="simple")
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="email")
    subject = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField(default="")
    is_premium = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} ({self.get_style_display()})"


# ═══════════════════════════ AUTOMATION RULES ═════════════════════════

class AutomationRule(models.Model):
    KEY_CHOICES = [
        ("reservation_pending_followup", "Relance réservation en attente"),
        ("booking_confirmed", "Confirmation réservation"),
        ("pre_start_reminder", "Rappel 24h avant location"),
        ("post_end_review", "Demande avis après location"),
        ("inactive_30d_offer", "Offre client inactif 30j"),
    ]
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
        ("both", "Email + WhatsApp"),
    ]

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="automation_rules")
    name = models.CharField(max_length=120, blank=True, default="")
    key = models.CharField(max_length=50, choices=KEY_CHOICES)
    enabled = models.BooleanField(default=False)
    dry_run = models.BooleanField(default=False)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="email")
    delay_minutes = models.PositiveIntegerField(default=0)
    delay_days = models.PositiveSmallIntegerField(default=0)
    template = models.ForeignKey(
        'MarketingTemplate', on_delete=models.SET_NULL,
        null=True, blank=True, related_name="automation_rules",
    )
    template_key = models.CharField(max_length=80, blank=True, default="")
    custom_content = models.TextField(blank=True, default="")
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        label = self.name or self.get_key_display()
        return f"{label} ({'ON' if self.enabled else 'OFF'})"

    @property
    def delay_hours(self):
        return self.delay_minutes // 60 if self.delay_minutes else self.delay_days * 24

    def get_trigger_display(self):
        return self.get_key_display()


# ═══════════════════════════ BANDIT (OPTIMISATION) ════════════════════

class BanditArm(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="bandit_arms")
    arm_key = models.CharField(max_length=120, db_index=True)
    pulls = models.PositiveIntegerField(default=0)
    rewards = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("agency", "arm_key")]
        ordering = ["-rewards"]

    def __str__(self):
        rate = (self.rewards / self.pulls * 100) if self.pulls else 0
        return f"{self.arm_key} — {rate:.0f}% ({self.pulls} pulls)"

    @property
    def conversion_rate(self):
        return self.rewards / self.pulls if self.pulls else 0.0


# ═══════════════════════════ WHATSAPP OUTBOX ══════════════════════════

class WhatsAppOutbox(models.Model):
    STATUS_CHOICES = [
        ("pending", "À envoyer"),
        ("sent", "Envoyé"),
        ("failed", "Échoué"),
    ]

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="wa_outbox")
    campaign = models.ForeignKey(MktCampaign, on_delete=models.SET_NULL, null=True, blank=True, related_name="wa_outbox")
    client = models.ForeignKey("clients.ClientAccount", on_delete=models.CASCADE, related_name="wa_outbox")
    phone = models.CharField(max_length=30)
    message = models.TextField()
    wa_link = models.URLField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "WhatsApp Outbox"
        verbose_name_plural = "WhatsApp Outbox"

    def __str__(self):
        return f"WA → {self.phone} ({self.get_status_display()})"
