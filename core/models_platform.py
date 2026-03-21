import logging

from django.db import models

logger = logging.getLogger(__name__)


class PlatformSettings(models.Model):
    """
    Singleton model for platform-wide configuration.
    Stores PayPal credentials (sandbox + live), domain, and other settings
    that can be changed from the SuperAdmin dashboard without redeploying.
    """

    PAYPAL_MODE_CHOICES = [
        ("sandbox", "Sandbox"),
        ("live", "Live"),
    ]

    singleton_id = models.PositiveSmallIntegerField(
        default=1, unique=True, editable=False,
    )

    # ── Domain ──────────────────────────────────────────────────────────
    public_base_url = models.URLField(
        blank=True, default="",
        help_text="URL publique de la plateforme (ex: https://app.gaboomdriveos.com)",
    )

    # ── PayPal — global ────────────────────────────────────────────────
    paypal_mode = models.CharField(
        max_length=10, choices=PAYPAL_MODE_CHOICES, default="sandbox",
    )
    enable_paypal_auto = models.BooleanField(
        default=False,
        help_text="Activer le paiement PayPal automatique pour les agences.",
    )
    paypal_webhook_verify = models.BooleanField(
        default=False,
        help_text="Activer la vérification de signature des webhooks PayPal.",
    )

    # ── PayPal — Sandbox ───────────────────────────────────────────────
    paypal_client_id_sandbox = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Client ID PayPal Sandbox.",
    )
    paypal_client_secret_sandbox_encrypted = models.TextField(
        blank=True, default="",
        help_text="Client Secret Sandbox chiffré via Fernet.",
    )
    paypal_product_id_sandbox = models.CharField(
        max_length=128, blank=True, default="",
        help_text="Product ID PayPal Sandbox (optionnel).",
    )
    paypal_plan_id_sandbox = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_webhook_id_sandbox = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Webhook ID PayPal Sandbox.",
    )

    # ── PayPal — Live ──────────────────────────────────────────────────
    paypal_client_id_live = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Client ID PayPal Live.",
    )
    paypal_client_secret_live_encrypted = models.TextField(
        blank=True, default="",
        help_text="Client Secret Live chiffré via Fernet.",
    )
    paypal_product_id_live = models.CharField(
        max_length=128, blank=True, default="",
        help_text="Product ID PayPal Live (optionnel).",
    )
    paypal_plan_id_live = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_plan_id_starter_sandbox = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_plan_id_starter_live = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_plan_id_business_sandbox = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_plan_id_business_live = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_plan_id_enterprise_sandbox = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_plan_id_enterprise_live = models.CharField(
        max_length=128, blank=True, default="",
    )
    paypal_webhook_id_live = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Webhook ID PayPal Live.",
    )
    SMTP_PROVIDER_CHOICES = [
        ("brevo_api", "Brevo API"),
        ("smtp", "SMTP"),
    ]
    smtp_provider = models.CharField(
        max_length=20, choices=SMTP_PROVIDER_CHOICES, default="brevo_api",
    )
    smtp_host = models.CharField(max_length=255, blank=True, default="")
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=255, blank=True, default="")
    smtp_password_encrypted = models.TextField(blank=True, default="")
    smtp_use_tls = models.BooleanField(default=True)
    smtp_use_ssl = models.BooleanField(default=False)
    smtp_from_email = models.EmailField(blank=True, default="")
    smtp_reply_to = models.EmailField(blank=True, default="")
    smtp_api_key_encrypted = models.TextField(blank=True, default="")

    master_code_encrypted = models.TextField(blank=True, default="")

    # ── Pricing ────────────────────────────────────────────────────────
    subscription_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=29.99,
        help_text="Prix mensuel de l'abonnement.",
    )
    subscription_currency = models.CharField(
        max_length=3, default="USD",
        help_text="Devise (USD, EUR, etc.).",
    )

    # ── Legacy single-mode fields (kept for migration compat) ─────────
    paypal_client_id = models.CharField(max_length=255, blank=True, default="")
    paypal_client_secret_encrypted = models.TextField(blank=True, default="")
    paypal_webhook_id = models.CharField(max_length=255, blank=True, default="")

    # ── Status / tracking ──────────────────────────────────────────────
    last_api_test_at = models.DateTimeField(null=True, blank=True)
    last_api_test_ok = models.BooleanField(default=False)
    last_webhook_received_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Platform Settings"
        verbose_name_plural = "Platform Settings"

    def __str__(self):
        return "PlatformSettings (singleton)"

    @classmethod
    def get(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _ = cls.objects.get_or_create(singleton_id=1)
        return obj

    # ── Mode-aware accessors ──────────────────────────────────────────

    @property
    def is_live(self) -> bool:
        return self.paypal_mode == "live"

    @property
    def active_client_id(self) -> str:
        if self.is_live:
            return self.paypal_client_id_live or self.paypal_client_id
        return self.paypal_client_id_sandbox or self.paypal_client_id

    @property
    def active_client_secret_encrypted(self) -> str:
        if self.is_live:
            return self.paypal_client_secret_live_encrypted or self.paypal_client_secret_encrypted
        return self.paypal_client_secret_sandbox_encrypted or self.paypal_client_secret_encrypted

    @property
    def active_plan_id(self) -> str:
        return self.paypal_plan_id_live if self.is_live else self.paypal_plan_id_sandbox

    @property
    def active_product_id(self) -> str:
        return self.paypal_product_id_live if self.is_live else self.paypal_product_id_sandbox

    @property
    def active_webhook_id(self) -> str:
        if self.is_live:
            return self.paypal_webhook_id_live or self.paypal_webhook_id
        return self.paypal_webhook_id_sandbox or self.paypal_webhook_id

    @property
    def smtp_api_key(self) -> str:
        return self._decrypt(self.smtp_api_key_encrypted)

    @property
    def smtp_password(self) -> str:
        return self._decrypt(self.smtp_password_encrypted)

    def set_smtp_password(self, value: str) -> None:
        self.smtp_password_encrypted = self._encrypt(value)

    @property
    def master_code(self) -> str:
        return self._decrypt(self.master_code_encrypted)

    def set_master_code(self, value: str) -> None:
        self.master_code_encrypted = self._encrypt(value)

    # ── Secret decrypt/encrypt ────────────────────────────────────────

    def _decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            from core.crypto import decrypt
            return decrypt(token)
        except Exception:
            logger.exception("Failed to decrypt PayPal secret")
            return ""

    def _encrypt(self, value: str) -> str:
        if not value:
            return ""
        from core.crypto import encrypt, ensure_fernet_key
        ensure_fernet_key()
        return encrypt(value)

    @property
    def active_client_secret(self) -> str:
        return self._decrypt(self.active_client_secret_encrypted)

    # Legacy property kept for backward compat
    @property
    def paypal_client_secret(self) -> str:
        return self.active_client_secret

    def set_secret(self, mode: str, value: str):
        """Encrypt and store secret for the given mode."""
        encrypted = self._encrypt(value)
        if mode == "live":
            self.paypal_client_secret_live_encrypted = encrypted
        else:
            self.paypal_client_secret_sandbox_encrypted = encrypted

    def set_smtp_api_key(self, value: str):
        self.smtp_api_key_encrypted = self._encrypt(value)

    # ── Dynamic URLs ───────────────────────────────────────────────────

    def get_paypal_api_base(self) -> str:
        if self.is_live:
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    # Keep old name for compat
    def get_paypal_base_url(self) -> str:
        return self.get_paypal_api_base()

    def get_webhook_url(self) -> str:
        if not self.public_base_url:
            return ""
        return f"{self.public_base_url.rstrip('/')}/webhooks/paypal/"


class EmailTemplate(models.Model):
    key = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=150, blank=True, default="")
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "Email Template"
        verbose_name_plural = "Email Templates"

    def __str__(self) -> str:
        return self.key


class EmailSendLog(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]
    template_key = models.CharField(max_length=80, blank=True, default="")
    to_email = models.EmailField()
    subject = models.CharField(max_length=255, blank=True, default="")
    provider = models.CharField(max_length=50, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    last_error = models.TextField(blank=True, default="")
    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email Log"
        verbose_name_plural = "Email Logs"

    def __str__(self) -> str:
        return f"{self.to_email} · {self.status}"
