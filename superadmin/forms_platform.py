from django import forms

from core.crypto import ensure_fernet_key, is_fernet_configured
from core.models_platform import PlatformSettings, EmailTemplate

_INPUT = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-sa-400 outline-none"
_MONO = f"{_INPUT} font-mono"
_SELECT = _INPUT
_CHECK = "rounded border-slate-300 text-sa-500 focus:ring-sa-500"


class PlatformSettingsForm(forms.ModelForm):
    """Form for editing PlatformSettings from the SuperAdmin dashboard (per-mode fields)."""

    paypal_client_secret_sandbox = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "off", "class": _MONO}),
        help_text="Laissez vide pour conserver le secret sandbox actuel.",
    )
    paypal_client_secret_live = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "off", "class": _MONO}),
        help_text="Laissez vide pour conserver le secret live actuel.",
    )
    smtp_provider = forms.ChoiceField(
        choices=PlatformSettings.SMTP_PROVIDER_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": _SELECT}),
    )
    smtp_host = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "smtp.brevo.com", "class": _INPUT}),
    )
    smtp_port = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={"class": _INPUT}),
    )
    smtp_username = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "login SMTP", "class": _INPUT}),
    )
    smtp_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "off", "class": _MONO}),
        help_text="Laissez vide pour conserver le mot de passe actuel.",
    )
    smtp_use_tls = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": _CHECK}))
    smtp_use_ssl = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": _CHECK}))
    smtp_from_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "no-reply@gaboomdriveos.com", "class": _INPUT}),
    )
    smtp_reply_to = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "support@gaboomdriveos.com", "class": _INPUT}),
    )
    smtp_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "off", "class": _MONO}),
        help_text="Laissez vide pour conserver la clé actuelle.",
    )

    class Meta:
        model = PlatformSettings
        fields = [
            "public_base_url",
            "paypal_mode",
            "enable_paypal_auto",
            "paypal_client_id_sandbox",
            "paypal_plan_id_sandbox",
            "paypal_product_id_sandbox",
            "paypal_webhook_id_sandbox",
            "paypal_client_id_live",
            "paypal_plan_id_live",
            "paypal_product_id_live",
            "paypal_webhook_id_live",
            "paypal_webhook_verify",
            "subscription_price",
            "subscription_currency",
            "smtp_provider",
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_use_tls",
            "smtp_use_ssl",
            "smtp_from_email",
            "smtp_reply_to",
        ]
        widgets = {
            "public_base_url": forms.URLInput(attrs={"placeholder": "https://app.gaboomdriveos.com", "class": _INPUT}),
            "paypal_mode": forms.Select(attrs={"class": _SELECT}),
            "enable_paypal_auto": forms.CheckboxInput(attrs={"class": _CHECK}),
            "paypal_client_id_sandbox": forms.TextInput(attrs={"placeholder": "AaBbCc...", "class": _MONO}),
            "paypal_plan_id_sandbox": forms.TextInput(attrs={"placeholder": "P-XXXXX...", "class": _MONO}),
            "paypal_product_id_sandbox": forms.TextInput(attrs={"placeholder": "PROD-XXXXX...", "class": _MONO}),
            "paypal_webhook_id_sandbox": forms.TextInput(attrs={"placeholder": "WH-XXXXX...", "class": _MONO}),
            "paypal_client_id_live": forms.TextInput(attrs={"placeholder": "AaBbCc...", "class": _MONO}),
            "paypal_plan_id_live": forms.TextInput(attrs={"placeholder": "P-XXXXX...", "class": _MONO}),
            "paypal_product_id_live": forms.TextInput(attrs={"placeholder": "PROD-XXXXX...", "class": _MONO}),
            "paypal_webhook_id_live": forms.TextInput(attrs={"placeholder": "WH-XXXXX...", "class": _MONO}),
            "paypal_webhook_verify": forms.CheckboxInput(attrs={"class": _CHECK}),
            "subscription_price": forms.NumberInput(attrs={"step": "0.01", "class": _INPUT}),
            "subscription_currency": forms.TextInput(attrs={"placeholder": "USD", "class": _INPUT, "maxlength": "3"}),
            "smtp_provider": forms.Select(attrs={"class": _SELECT}),
            "smtp_host": forms.TextInput(attrs={"placeholder": "smtp.brevo.com", "class": _INPUT}),
            "smtp_port": forms.NumberInput(attrs={"class": _INPUT}),
            "smtp_username": forms.TextInput(attrs={"class": _INPUT}),
            "smtp_use_tls": forms.CheckboxInput(attrs={"class": _CHECK}),
            "smtp_use_ssl": forms.CheckboxInput(attrs={"class": _CHECK}),
            "smtp_from_email": forms.EmailInput(attrs={"class": _INPUT}),
            "smtp_reply_to": forms.EmailInput(attrs={"class": _INPUT}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Encrypt secrets per mode
        for mode in ("sandbox", "live"):
            secret = self.cleaned_data.get(f"paypal_client_secret_{mode}", "").strip()
            if secret:
                if not is_fernet_configured():
                    ensure_fernet_key()
                instance.set_secret(mode, secret)
        smtp_key = self.cleaned_data.get("smtp_api_key", "").strip()
        if smtp_key:
            if not is_fernet_configured():
                ensure_fernet_key()
            instance.set_smtp_api_key(smtp_key)
        port = self.cleaned_data.get("smtp_port", None)
        if port:
            instance.smtp_port = port
        elif instance.smtp_port is None:
            instance.smtp_port = 587
        smtp_password = self.cleaned_data.get("smtp_password", "").strip()
        if smtp_password:
            if not is_fernet_configured():
                ensure_fernet_key()
            instance.set_smtp_password(smtp_password)
        if commit:
            instance.save()
        return instance


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ["key", "name", "subject", "body_text", "body_html", "is_active"]
        widgets = {
            "key": forms.TextInput(attrs={"class": _MONO}),
            "name": forms.TextInput(attrs={"class": _INPUT}),
            "subject": forms.TextInput(attrs={"class": _INPUT}),
            "body_text": forms.Textarea(attrs={"class": _INPUT, "rows": 6}),
            "body_html": forms.Textarea(attrs={"class": _INPUT, "rows": 6}),
        }
