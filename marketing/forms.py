
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify

from agencies.models import Agency
from agencies.services import PLAN_CONFIGS, apply_plan_to_access, get_agency_access

User = get_user_model()


class AgencySignupForm(forms.Form):
    agency_name = forms.CharField(
        max_length=255,
        error_messages={"required": "Le nom de l'agence est requis."},
    )
    slug = forms.SlugField(
        max_length=150,
        required=False,
        help_text="Identifiant URL de votre agence. Généré automatiquement si vide.",
    )
    city = forms.CharField(max_length=100, required=False)
    phone = forms.CharField(max_length=30, required=False)
    plan_code = forms.ChoiceField(
        choices=[(k, v["name"]) for k, v in PLAN_CONFIGS.items()],
        error_messages={"required": "Veuillez choisir un plan."},
    )

    email = forms.EmailField(
        error_messages={"required": "L'email est requis.", "invalid": "Email invalide."},
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(),
        error_messages={"required": "Le mot de passe est requis."},
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(),
        error_messages={"required": "Confirmez le mot de passe."},
    )
    accept_terms = forms.BooleanField(
        required=True,
        error_messages={"required": "Vous devez accepter les conditions d'utilisation."},
    )

    def clean_slug(self):
        raw = self.cleaned_data.get("slug", "").strip()
        if not raw:
            return ""
        slug = slugify(raw)
        if not slug:
            raise forms.ValidationError("Le slug contient des caractères invalides.")
        if Agency.objects.filter(slug=slug).exists():
            raise forms.ValidationError("Ce lien est déjà utilisé, choisissez-en un autre.")
        return slug

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte avec cet email existe déjà.")
        return email

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        plan_code = cleaned.get("plan_code")
        if plan_code not in PLAN_CONFIGS:
            self.add_error("plan_code", "Veuillez choisir un plan valide.")
        return cleaned

    def save(self):
        agency_name = self.cleaned_data["agency_name"].strip()
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        city = self.cleaned_data.get("city", "").strip()
        phone = self.cleaned_data.get("phone", "").strip()
        plan_code = self.cleaned_data["plan_code"]

        slug = self.cleaned_data.get("slug") or ""
        if not slug:
            base_slug = slugify(agency_name) or "agency"
            slug = base_slug
            i = 1
            while Agency.objects.filter(slug=slug).exists():
                i += 1
                slug = f"{base_slug}-{i}"

        agency = Agency.objects.create(
            name=agency_name,
            slug=slug,
            public_city=city,
            public_phone=phone,
            public_whatsapp=phone,
            public_enabled=True,
        )

        username = email
        if User.objects.filter(username=username).exists():
            username = f"{email.split('@')[0]}-{agency.slug}"

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role="agency_owner",
            agency=agency,
        )
        access = get_agency_access(agency)
        apply_plan_to_access(access, plan_code)
        return agency, user
