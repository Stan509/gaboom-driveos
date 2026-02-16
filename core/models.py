from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    # ── Official RBAC roles ──────────────────────────────────────────
    ROLE_CHOICES = [
        ("agency_owner", "Propri\u00e9taire"),
        ("agency_manager", "Manager"),
        ("agency_secretary", "Secr\u00e9taire"),
        ("agency_accountant", "Comptable"),
        ("agency_staff", "Employ\u00e9"),
        ("read_only", "Lecture seule"),
    ]


    role = models.CharField(
        max_length=30, choices=ROLE_CHOICES, default="agency_owner",
        help_text="R\u00f4le RBAC officiel",
    )

    use_custom_permissions = models.BooleanField(default=False)
    granted_permissions = models.ManyToManyField(
        "agencies.Permission", related_name="granted_to", blank=True,
    )
    revoked_permissions = models.ManyToManyField(
        "agencies.Permission", related_name="revoked_from", blank=True,
    )

    email_verified = models.BooleanField(default=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    whatsapp = models.CharField(max_length=30, blank=True, default="")
    agency = models.ForeignKey(
        "agencies.Agency",
        related_name="users",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(is_superuser=True)
                    | ~models.Q(agency__isnull=True)
                ),
                name="non_superuser_must_have_agency",
            ),
        ]

    @property
    def is_owner(self):
        return self.role == "agency_owner"

    @property
    def role_label(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)

    def clean(self):
        super().clean()
        if not self.is_superuser and self.agency_id is None:
            raise ValidationError(
                {"agency": "Un utilisateur non-superuser doit \u00eatre rattach\u00e9 \u00e0 une agence."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
