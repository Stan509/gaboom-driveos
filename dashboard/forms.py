from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from agencies.models import Agency, AgencySiteSettings, BusinessSettings, MaintenanceRecord, Vehicle
from agencies.services import get_agency_access
from billing.models import Contract, Payment
from clients.models import Client
from core.models import User

_INPUT = "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-violet-400 focus:ring-1 focus:ring-violet-400 outline-none"
_CHECK = "rounded border-slate-300 text-gaboomViolet focus:ring-violet-400"
_FILE = "text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-violet-50 file:text-gaboomViolet hover:file:bg-violet-100"


# ═══════════════════════ Account Profile ═════════════════════════════════

class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "phone", "whatsapp"]
        labels = {
            "full_name": _("Nom complet"),
            "phone": _("Téléphone"),
            "whatsapp": _("WhatsApp"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = _INPUT


# ═══════════════════════ Agency Profile ═══════════════════════════════════

_ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


class AgencyProfileForm(forms.ModelForm):
    class Meta:
        model = Agency
        fields = [
            "logo", "name", "slogan",
            "contact_email", "phone", "whatsapp",
            "address_line1", "address_line2", "city", "country",
            "website_url",
            "legal_name", "tax_id", "currency", "invoice_footer",
        ]
        labels = {
            "logo": _("Logo"),
            "name": _("Nom commercial"),
            "slogan": _("Slogan"),
            "contact_email": _("Email de contact"),
            "phone": _("Téléphone"),
            "whatsapp": _("WhatsApp"),
            "address_line1": _("Adresse ligne 1"),
            "address_line2": _("Adresse ligne 2"),
            "city": _("Ville"),
            "country": _("Pays"),
            "website_url": _("Site web"),
            "legal_name": _("Raison sociale"),
            "tax_id": _("N° TVA / SIRET"),
            "currency": _("Devise"),
            "invoice_footer": _("Pied de facture"),
        }
        widgets = {
            "invoice_footer": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, role="agency_staff", **kwargs):
        super().__init__(*args, **kwargs)
        # Styling
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs["class"] = _FILE
                field.widget.attrs["accept"] = "image/png,image/jpeg,image/webp"
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", _INPUT)
            else:
                field.widget.attrs["class"] = _INPUT

        # Role-based restrictions
        owner_only = ["legal_name", "tax_id", "currency", "invoice_footer", "name"]
        if role != "agency_owner":
            for fname in owner_only:
                if fname in self.fields:
                    self.fields[fname].disabled = True

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "content_type"):
            if logo.content_type not in _ALLOWED_IMAGE_TYPES:
                raise ValidationError("Format accepté : PNG, JPG ou WebP.")
            if logo.size > _MAX_IMAGE_SIZE:
                raise ValidationError("Le logo ne doit pas dépasser 5 Mo.")
        return logo


# ═══════════════════════ Team Member ═══════════════════════════════════

class TeamMemberCreateForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "membre@example.com"}),
    )
    full_name = forms.CharField(
        label="Nom complet", required=False,
        widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Jean Dupont"}),
    )
    phone = forms.CharField(
        label="Téléphone", required=False,
        widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "+33 6 …"}),
    )
    role = forms.ChoiceField(
        label="Rôle",
        choices=[],
        widget=forms.Select(attrs={"class": _INPUT}),
    )

    def __init__(self, *args, current_role="agency_staff", agency=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._agency = agency
        
        # Define allowed roles based on creator's role
        allowed_roles = []
        if current_role == "agency_owner":
            # Owner can create any role except another owner (usually)
            allowed_roles = [
                r for r in User.ROLE_CHOICES 
                if r[0] != "agency_owner"
            ]
        elif current_role == "agency_manager":
            # Manager can create operational staff
            allowed_roles = [
                r for r in User.ROLE_CHOICES 
                if r[0] in ("agency_secretary", "agency_accountant", "agency_staff", "read_only")
            ]
            
        self.fields["role"].choices = allowed_roles
        if not allowed_roles:
            self.fields["role"].disabled = True

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("Un utilisateur avec cet email existe déjà.")
        return email

    def clean(self):
        cleaned = super().clean()
        if self._agency:
            access = get_agency_access(self._agency)
            if access.max_users and self._agency.users.count() >= access.max_users:
                self.add_error(None, "Limite d'utilisateurs atteinte pour votre plan.")
        return cleaned


class TeamMemberEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "phone", "whatsapp", "role"]
        labels = {
            "full_name": "Nom complet",
            "phone": "Téléphone",
            "whatsapp": "WhatsApp",
            "role": "Rôle",
        }

    def __init__(self, *args, current_role="agency_staff", **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = _INPUT
            
        # Define allowed roles based on editor's role
        allowed_roles = []
        if current_role == "agency_owner":
            allowed_roles = [
                r for r in User.ROLE_CHOICES 
                if r[0] != "agency_owner"
            ]
            # If editing self or another owner, maybe handle differently? 
            # For now, assuming editing SUBORDINATES.
        elif current_role == "agency_manager":
            allowed_roles = [
                r for r in User.ROLE_CHOICES 
                if r[0] in ("agency_secretary", "agency_accountant", "agency_staff", "read_only")
            ]
            
        self.fields["role"].choices = allowed_roles
        
        # If the user being edited has a role higher/equal to current user, disable role editing?
        # Ideally logic should be in view, but here we just set choices.
        if not allowed_roles:
            self.fields["role"].disabled = True


# ═══════════════════════ Vehicle ═══════════════════════════════════════

class VehicleForm(forms.ModelForm):
    STATUS_CHOICES = [
        ("available", "Disponible"),
        ("rented", "En location"),
        ("maintenance", "Maintenance"),
    ]

    class Meta:
        model = Vehicle
        fields = ["make", "model", "plate_number", "daily_price", "status",
                  "public_visible", "allow_negotiation", "image", "current_km",
                  "gps_imei", "gps_ip", "gps_source", "gps_enabled"]
        labels = {
            "make": "Marque", "model": "Modèle", "plate_number": "Immatriculation",
            "daily_price": "Prix / jour (€)", "status": "Statut",
            "public_visible": "Visible sur le site public",
            "allow_negotiation": "Autoriser négociation prix",
            "image": "Photo",
            "current_km": "Kilométrage actuel",
            "gps_imei": "IMEI GPS",
            "gps_ip": "IP du tracker GPS",
            "gps_source": "Source GPS",
            "gps_enabled": "GPS activé",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = _CHECK
            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs["class"] = _FILE
                field.widget.attrs["accept"] = "image/png,image/jpeg,image/webp"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = _INPUT
            else:
                field.widget.attrs["class"] = _INPUT
        self.fields["status"].widget = forms.Select(choices=self.STATUS_CHOICES, attrs={"class": _INPUT})

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "content_type"):
            if image.content_type not in _ALLOWED_IMAGE_TYPES:
                raise ValidationError("Format accepté : PNG, JPG ou WebP.")
            if image.size > _MAX_IMAGE_SIZE:
                raise ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return image


# ═══════════════════════ Client ════════════════════════════════════════

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["full_name", "email", "phone", "whatsapp", "address",
                  "driving_license_number", "driving_license_expiry", "id_document",
                  "notes", "tags", "status", "follow_up_at", "follow_up_note"]
        labels = {
            "full_name": "Nom complet", "email": "Email", "phone": "Téléphone",
            "whatsapp": "WhatsApp", "address": "Adresse", "notes": "Notes",
            "driving_license_number": "N° permis de conduire",
            "driving_license_expiry": "Expiration permis",
            "id_document": "Pièce d'identité (photo)",
            "tags": "Tags (séparés par virgule)", "status": "Statut",
            "follow_up_at": "Prochaine relance", "follow_up_note": "Note relance",
        }
        widgets = {
            "follow_up_at": forms.DateInput(attrs={"type": "date"}),
            "driving_license_expiry": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs["class"] = _FILE
            elif isinstance(field.widget, (forms.Textarea,)):
                field.widget.attrs.setdefault("class", _INPUT)
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = _INPUT
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = _CHECK
            else:
                field.widget.attrs["class"] = _INPUT

    def clean_id_document(self):
        f = self.cleaned_data.get("id_document")
        if f and hasattr(f, "size"):
            if f.size > 5 * 1024 * 1024:
                raise ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
            ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
            if ext not in ("png", "jpg", "jpeg", "webp"):
                raise ValidationError("Formats acceptés : PNG, JPG, WebP.")
        return f


# ═══════════════════════ Contract ══════════════════════════════════════

class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = [
            "client", "vehicle", "start_date", "end_date", "status",
            "price_per_day", "deposit", "km_depart", "fuel_depart",
            "km_included", "km_price", "fuel_fee", "late_fee",
            "pickup_datetime", "return_datetime",
            "contract_clause", "penalty_clause", "gps_clause",
            "notes",
        ]
        labels = {
            "client": "Client", "vehicle": "Véhicule",
            "start_date": "Date début", "end_date": "Date fin",
            "status": "Statut",
            "price_per_day": "Prix / jour", "deposit": "Caution",
            "km_depart": "Km départ", "fuel_depart": "Jauge carburant (1-8)",
            "km_included": "Km inclus", "km_price": "Prix km sup.",
            "fuel_fee": "Frais carburant", "late_fee": "Frais retard / jour",
            "pickup_datetime": "Date/heure de remise",
            "return_datetime": "Date/heure de retour prévue",
            "contract_clause": "Clause du contrat",
            "penalty_clause": "Clause de pénalité",
            "gps_clause": "Clause GPS / géolocalisation",
            "notes": "Notes",
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "pickup_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "return_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "contract_clause": forms.Textarea(attrs={"rows": 4}),
            "penalty_clause": forms.Textarea(attrs={"rows": 3}),
            "gps_clause": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, agency=None, **kwargs):
        self._agency = agency
        super().__init__(*args, **kwargs)
        if agency:
            self.fields["client"].queryset = Client.objects.for_agency(agency)
            # In edit mode, allow the already-assigned vehicle even if not available
            if self.instance and self.instance.pk:
                self.fields["vehicle"].queryset = Vehicle.objects.for_agency(agency)
            else:
                self.fields["vehicle"].queryset = Vehicle.objects.for_agency(agency).filter(
                    status="available"
                )
            # Pre-fill defaults from BusinessSettings
            if not self.instance.pk:
                try:
                    bs = agency.business_settings
                    defaults = {
                        "km_included": bs.km_included,
                        "km_price": bs.km_extra_price,
                        "fuel_fee": bs.fuel_fee,
                        "late_fee": bs.late_fee_per_day,
                        "deposit": bs.deposit_default,
                        "contract_clause": bs.default_contract_clause,
                        "penalty_clause": bs.default_penalty_clause,
                    }
                    for k, v in defaults.items():
                        if v is not None and k in self.fields:
                            self.fields[k].initial = v
                except Exception:
                    pass
        # Limit status choices for creation
        if self.instance and self.instance.pk:
            self.fields["status"].widget = forms.Select(
                choices=[
                    ("draft", "Brouillon"), ("pending_signature", "En attente de signature"),
                    ("active", "Actif"), ("pending_return", "Retour en cours"),
                ],
                attrs={"class": _INPUT},
            )
        else:
            self.fields["status"].widget = forms.Select(
                choices=[("draft", "Brouillon"), ("pending_signature", "En attente de signature")],
                attrs={"class": _INPUT},
            )
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", _INPUT)
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", _INPUT)
            else:
                field.widget.attrs.setdefault("class", _INPUT)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        vehicle = cleaned.get("vehicle")

        if start and end and end < start:
            self.add_error("end_date", "La date de fin doit être après la date de début.")

        # Overlap check: no active/draft contract for same vehicle on overlapping dates
        if start and end and vehicle:
            overlap_qs = Contract.objects.filter(
                vehicle=vehicle,
                status__in=("draft", "active"),
                start_date__lt=end,
                end_date__gt=start,
            )
            if self.instance and self.instance.pk:
                overlap_qs = overlap_qs.exclude(pk=self.instance.pk)
            if self._agency:
                overlap_qs = overlap_qs.filter(agency=self._agency)
            if overlap_qs.exists():
                self.add_error(
                    "vehicle",
                    "Ce véhicule est déjà réservé sur cette période.",
                )
        return cleaned


# ═══════════════════════ Payment ═══════════════════════════════════════

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "reference", "note"]
        labels = {
            "amount": "Montant", "method": "Méthode",
            "reference": "Référence", "note": "Note",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = _INPUT
            else:
                field.widget.attrs["class"] = _INPUT


# ═══════════════════════ Business Settings ════════════════════════════

class BusinessSettingsForm(forms.ModelForm):
    class Meta:
        model = BusinessSettings
        exclude = ["agency"]
        labels = {
            # Widget 1
            "km_included": "Km inclus",
            "km_type": "Type km inclus",
            "km_unlimited": "Km illimité",
            "km_extra_price": "Prix km supplémentaire",
            "late_tolerance_minutes": "Tolérance retard (min)",
            "late_billing_mode": "Facturation retard",
            "late_fee_per_day": "Frais retard / jour",
            "fuel_policy": "Politique carburant",
            "fuel_fee": "Frais carburant",
            "vat_percent": "TVA (%)",
            "currency": "Devise",
            "invoice_rounding": "Arrondi facturation",
            # Widget 2
            "deposit_default": "Dépôt de garantie",
            "deposit_mode": "Mode dépôt",
            "insurance_franchise": "Franchise assurance",
            "insurance_included": "Assurance incluse",
            "franchise_buyback": "Rachat de franchise possible",
            "franchise_buyback_price": "Prix rachat franchise / jour",
            # Widget 3
            "auto_number_contracts": "Numérotation auto contrats",
            "auto_number_invoices": "Numérotation auto factures",
            "contract_prefix": "Préfixe contrat",
            "invoice_prefix": "Préfixe facture",
            "pay_cash": "Espèce",
            "pay_card": "Carte bancaire",
            "pay_transfer": "Virement",
            "pay_mobile_money": "Mobile money",
            "partial_payment_allowed": "Paiement partiel autorisé",
            "invoice_due_days": "Délai paiement facture (jours)",
            # Widget 4
            "maintenance_interval_km": "Intervalle maintenance (km)",
            "maintenance_interval_months": "Intervalle maintenance (mois)",
            "maintenance_alert_km": "Alerte maintenance X km avant",
            "maintenance_alert_days": "Alerte maintenance X jours avant",
            "maintenance_grace_km": "Tolérance dépassement (km)",
            "maintenance_email_alert": "Email alerte automatique",
            "maintenance_disable_vehicle": "Désactiver véhicule si maintenance dépassée",
            # Widget 5
            "allow_price_negotiation": "Activer la négociation de prix",
            "negotiation_min_percent": "Offre minimum (% du prix)",
            # Widget 6
            "default_contract_clause": "Clause de contrat par défaut",
            "default_penalty_clause": "Clause de pénalité par défaut",
            # Widget 7 — GPS
            "gps_tracking_enabled": "Activer le suivi GPS",
            "gps_speed_limit": "Limite de vitesse (km/h)",
            "gps_offline_alert_minutes": "Alerte GPS hors ligne (minutes)",
            "default_gps_clause": "Clause GPS par défaut",
        }
        widgets = {
            "default_contract_clause": forms.Textarea(attrs={"rows": 6}),
            "default_penalty_clause": forms.Textarea(attrs={"rows": 4}),
            "default_gps_clause": forms.Textarea(attrs={"rows": 5}),
        }

    # Field grouping for template rendering
    WIDGET_FIELDS = {
        "contracts": [
            "km_included", "km_type", "km_unlimited", "km_extra_price",
            "late_tolerance_minutes", "late_billing_mode", "late_fee_per_day",
            "fuel_policy", "fuel_fee", "vat_percent", "currency", "invoice_rounding",
        ],
        "insurance": [
            "deposit_default", "deposit_mode", "insurance_franchise",
            "insurance_included", "franchise_buyback", "franchise_buyback_price",
        ],
        "billing": [
            "auto_number_contracts", "auto_number_invoices",
            "contract_prefix", "invoice_prefix",
            "pay_cash", "pay_card", "pay_transfer", "pay_mobile_money",
            "partial_payment_allowed", "invoice_due_days",
        ],
        "maintenance": [
            "maintenance_interval_km", "maintenance_interval_months",
            "maintenance_alert_km", "maintenance_alert_days",
            "maintenance_grace_km",
            "maintenance_email_alert", "maintenance_disable_vehicle",
        ],
        "negotiation": [
            "allow_price_negotiation", "negotiation_min_percent",
        ],
        "clauses": [
            "default_contract_clause", "default_penalty_clause",
        ],
        "gps": [
            "gps_tracking_enabled", "gps_speed_limit",
            "gps_offline_alert_minutes", "default_gps_clause",
        ],
    }

    def __init__(self, *args, readonly=False, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = _CHECK
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = _INPUT
            else:
                field.widget.attrs["class"] = _INPUT
            if readonly:
                field.disabled = True

    def clean(self):
        cleaned = super().clean()
        # Ensure numeric fields are non-negative
        numeric_fields = [
            "km_included", "km_extra_price", "late_tolerance_minutes",
            "late_fee_per_day", "fuel_fee", "vat_percent",
            "deposit_default", "insurance_franchise", "franchise_buyback_price",
            "invoice_due_days", "maintenance_interval_km",
            "maintenance_interval_months", "maintenance_alert_km",
            "maintenance_alert_days", "maintenance_grace_km",
            "negotiation_min_percent",
        ]
        for fname in numeric_fields:
            val = cleaned.get(fname)
            if val is not None and val < 0:
                self.add_error(fname, "La valeur doit être positive.")
        return cleaned

    @property
    def fields_for_widget(self):
        """Return a dict mapping widget keys to lists of BoundField objects.
        Accessible in templates as {{ form.fields_for_widget.contracts }}."""
        result = {}
        for key, names in self.WIDGET_FIELDS.items():
            result[key] = [self[n] for n in names if n in self.fields]
        return result


# ═══════════════════════ Maintenance ═════════════════════════════════

class MaintenanceRecordForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = ["date", "km_at_service", "service_type", "cost", "notes"]
        labels = {
            "date": "Date de l'intervention",
            "km_at_service": "Kilométrage au moment de l'entretien",
            "service_type": "Type d'intervention",
            "cost": "Coût (€)",
            "notes": "Notes",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", _INPUT)
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = _INPUT
            else:
                field.widget.attrs["class"] = _INPUT

    def clean_km_at_service(self):
        km = self.cleaned_data.get("km_at_service")
        if km is not None and km < 0:
            raise ValidationError("Le kilométrage doit être positif.")
        return km

    def clean_cost(self):
        cost = self.cleaned_data.get("cost")
        if cost is not None and cost < 0:
            raise ValidationError("Le coût doit être positif.")
        return cost


class UpdateKmForm(forms.Form):
    current_km = forms.IntegerField(
        label="Kilométrage actuel",
        min_value=0,
        widget=forms.NumberInput(attrs={"class": _INPUT}),
    )


# ═══════════════════════ Site Builder ═════════════════════════════════

_ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5 MB

class AgencySiteSettingsForm(forms.ModelForm):
    class Meta:
        model = AgencySiteSettings
        fields = [
            "is_public_enabled", "is_maintenance_enabled",
            "theme_key", "primary_color", "secondary_color", "font_family",
            "hero_title", "hero_subtitle", "cta_text",
            "city", "contact_phone", "whatsapp", "contact_email",
            "logo",
            "seo_title", "seo_description",
        ]
        labels = {
            "is_public_enabled": "Site public activé",
            "is_maintenance_enabled": "Mode maintenance",
            "theme_key": "Thème",
            "primary_color": "Couleur primaire",
            "secondary_color": "Couleur secondaire",
            "font_family": "Police",
            "hero_title": "Titre principal",
            "hero_subtitle": "Sous-titre",
            "cta_text": "Texte du bouton",
            "city": "Ville",
            "contact_phone": "Téléphone",
            "whatsapp": "WhatsApp",
            "contact_email": "Email de contact",
            "logo": "Logo",
            "seo_title": "Titre SEO",
            "seo_description": "Description SEO",
        }
        widgets = {
            "logo": forms.ClearableFileInput(attrs={"class": _FILE}),
            "primary_color": forms.TextInput(attrs={"type": "color", "class": "h-8 w-10 rounded border border-slate-200 cursor-pointer p-0"}),
            "secondary_color": forms.TextInput(attrs={"type": "color", "class": "h-8 w-10 rounded border border-slate-200 cursor-pointer p-0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in ("is_public_enabled", "is_maintenance_enabled"):
                continue
            if name in ("logo", "primary_color", "secondary_color"):
                continue
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = _INPUT

    def clean_primary_color(self):
        import re
        c = self.cleaned_data.get("primary_color", "").strip()
        if c and not re.match(r"^#[0-9A-Fa-f]{6}$", c):
            raise ValidationError("Couleur invalide (format #RRGGBB).")
        return c or "#6D28D9"

    def clean_secondary_color(self):
        import re
        c = self.cleaned_data.get("secondary_color", "").strip()
        if c and not re.match(r"^#[0-9A-Fa-f]{6}$", c):
            raise ValidationError("Couleur invalide (format #RRGGBB).")
        return c or "#FACC15"

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "content_type"):
            if logo.content_type not in _ALLOWED_LOGO_TYPES:
                raise ValidationError("Format accepté : PNG, JPG ou WebP.")
            if logo.size > _MAX_LOGO_SIZE:
                raise ValidationError("Le logo ne doit pas dépasser 5 Mo.")
        return logo
