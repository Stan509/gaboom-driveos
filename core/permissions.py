"""
RBAC permission system for GaboomDriveOS.

Official roles:
  SUPERADMIN       (is_superuser=True)
  AGENCY_OWNER     full access to own agency
  AGENCY_MANAGER   broad access, no settings/team/site
  AGENCY_SECRETARY clients, contracts, reservations, vehicles (view)
  AGENCY_ACCOUNTANT billing, contracts, vehicles/clients (view)
  AGENCY_STAFF     view most modules
  READ_ONLY        view only

Permission keys are dotted strings (e.g. "clients.view").
"""

import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from agencies.services import get_agency_access, get_plan_config
logger = logging.getLogger("gaboom.rbac")


# ── Complete permission catalogue ──────────────────────────────────────
# (key, label, group)

ALL_PERMISSIONS = [
    # Dashboard
    ("dashboard.view", "Voir le dashboard", "Dashboard"),
    # Vehicles
    ("vehicles.view", "Voir les vehicules", "Vehicules"),
    ("vehicles.create", "Ajouter un vehicule", "Vehicules"),
    ("vehicles.edit", "Modifier un vehicule", "Vehicules"),
    ("vehicles.delete", "Supprimer un vehicule", "Vehicules"),
    ("vehicles.publish", "Publier / depublier (site public)", "Vehicules"),
    # Clients
    ("clients.view", "Voir les clients", "Clients"),
    ("clients.create", "Ajouter un client", "Clients"),
    ("clients.edit", "Modifier un client", "Clients"),
    ("clients.delete", "Supprimer un client", "Clients"),
    ("clients.export", "Exporter les clients", "Clients"),
    # Contracts
    ("contracts.view", "Voir les contrats", "Contrats"),
    ("contracts.create", "Creer un contrat", "Contrats"),
    ("contracts.edit", "Modifier / cloturer un contrat", "Contrats"),
    ("contracts.cancel", "Annuler un contrat", "Contrats"),
    ("contracts.export", "Exporter les contrats", "Contrats"),
    # Billing / Payments
    ("billing.view", "Voir les paiements", "Paiements"),
    ("billing.create", "Enregistrer un paiement", "Paiements"),
    ("billing.refund", "Rembourser un paiement", "Paiements"),
    ("billing.export", "Exporter les paiements", "Paiements"),
    # Reservations
    ("reservations.view", "Voir les reservations", "Reservations"),
    ("reservations.manage", "Confirmer / refuser les reservations", "Reservations"),
    # Maintenance
    ("maintenance.view", "Voir la maintenance", "Maintenance"),
    ("maintenance.toggle", "Marquer maintenance effectuee", "Maintenance"),
    # GPS
    ("gps.view", "Voir le GPS", "GPS"),
    ("gps.manage_devices", "Gerer les boitiers GPS", "GPS"),
    ("gps.manage_zones", "Gerer les zones GPS", "GPS"),
    # Public Site
    ("public_site.view", "Voir le site public", "Site public"),
    ("public_site.edit", "Modifier titre, slogan, theme", "Site public"),
    ("public_site.publish", "Mettre en ligne / maintenance", "Site public"),
    ("public_site.assets_upload", "Uploader logo / medias", "Site public"),
    ("public_site.leads.view", "Voir les demandes / contacts", "Site public"),
    ("public_site.leads.reply", "Repondre aux demandes", "Site public"),
    # Marketing
    ("marketing.view", "Voir le marketing", "Marketing"),
    ("marketing.edit", "Gerer les campagnes / automations", "Marketing"),
    # Promotions
    ("promotions.view", "Voir les promotions", "Promotions"),
    ("promotions.edit", "Gerer les codes promo / bannieres", "Promotions"),
    # Team
    ("team.view", "Voir l'equipe", "Equipe"),
    ("team.create", "Ajouter un membre", "Equipe"),
    ("team.edit", "Modifier un membre", "Equipe"),
    ("team.deactivate", "Desactiver un membre", "Equipe"),
    ("team.delete", "Supprimer un membre", "Equipe"),
    ("team.permissions_manage", "Gerer rang / permissions d'un membre", "Equipe"),
    # Settings (owner-only by default)
    ("settings.view", "Voir les parametres metier", "Parametres"),
    ("settings.edit", "Modifier les parametres metier", "Parametres"),
    # Subscription
    ("subscription.view", "Voir l'abonnement", "Abonnement"),
]

PERMISSION_CODES = [code for code, _, _ in ALL_PERMISSIONS]
PERMISSION_LABELS = {code: label for code, label, _ in ALL_PERMISSIONS}

# Grouped for UI display (ordered)
PERMISSION_GROUPS: dict[str, list[tuple[str, str]]] = {}
for _code, _label, _group in ALL_PERMISSIONS:
    PERMISSION_GROUPS.setdefault(_group, []).append((_code, _label))


# ══════════════════════════════════════════════════════════════════════
# OFFICIAL ROLE → PERMISSION MATRIX
# ══════════════════════════════════════════════════════════════════════

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "agency_owner": list(PERMISSION_CODES),  # full access

    "agency_manager": [
        "dashboard.view",
        "vehicles.view", "vehicles.create", "vehicles.edit",
        "clients.view", "clients.create", "clients.edit",
        "contracts.view", "contracts.create", "contracts.edit", "contracts.cancel", "contracts.export",
        "billing.view",
        "reservations.view", "reservations.manage",
        "maintenance.view", "maintenance.toggle",
        "gps.view", "gps.manage_devices", "gps.manage_zones",
        "public_site.view",
        "marketing.view", "marketing.edit",
        "promotions.view",
        "subscription.view",
    ],

    "agency_secretary": [
        "dashboard.view",
        "vehicles.view",
        "clients.view", "clients.create", "clients.edit",
        "contracts.view", "contracts.create", "contracts.edit", "contracts.cancel", "contracts.export",
        "billing.view",
        "reservations.view", "reservations.manage",
        "maintenance.view",
        "gps.view",
    ],

    "agency_accountant": [
        "dashboard.view",
        "vehicles.view",
        "clients.view",
        "contracts.view", "contracts.create", "contracts.edit", "contracts.cancel", "contracts.export",
        "billing.view", "billing.create", "billing.refund", "billing.export",
        "reservations.view",
        "maintenance.view",
        "gps.view",
    ],

    "agency_staff": [
        "dashboard.view",
        "vehicles.view",
        "clients.view",
        "contracts.view",
        "reservations.view",
        "maintenance.view",
        "gps.view",
    ],

    "read_only": [
        "dashboard.view",
        "vehicles.view",
        "clients.view",
        "contracts.view",
        "billing.view",
        "reservations.view",
        "maintenance.view",
        "gps.view",
        "subscription.view",
    ],
}

ROLE_LABELS = {
    "agency_owner": "Proprietaire",
    "agency_manager": "Manager",
    "agency_secretary": "Secretaire",
    "agency_accountant": "Comptable",
    "agency_staff": "Employe",
    "read_only": "Lecture seule",
}


# ── Runtime helpers ────────────────────────────────────────────────────

def get_effective_permissions(user) -> set[str]:
    """Return the effective set of permission codes for *user*."""
    if not user or not user.is_authenticated:
        return set()
    # Superuser → full access
    if user.is_superuser:
        return set(PERMISSION_CODES)

    # New role-based system (primary)
    role = getattr(user, "role", "") or ""
    if role and role in ROLE_PERMISSIONS:
        base = set(ROLE_PERMISSIONS[role])
    else:
        # Default fallback for unknown/missing roles
        base = set()

    base.add("dashboard.view")  # always granted

    # Custom overrides
    if getattr(user, "use_custom_permissions", False):
        grants = set(user.granted_permissions.values_list("key", flat=True))
        revokes = set(user.revoked_permissions.values_list("key", flat=True))
        base = (base | grants) - revokes
    if getattr(user, "agency_id", None):
        access = get_agency_access(user.agency)
        plan = get_plan_config(access.plan_code)
        features = plan["features"]
        if not features.get("public_site"):
            base -= {
                "public_site.view", "public_site.edit",
                "public_site.publish", "public_site.assets_upload",
                "public_site.leads.view", "public_site.leads.reply",
            }
        if not features.get("marketing_tools"):
            base -= {
                "marketing.view", "marketing.edit",
                "promotions.view", "promotions.edit",
            }
    return base


def has_perm(user, code: str) -> bool:
    """Check if *user* has a specific permission."""
    return code in get_effective_permissions(user)


def require_perm(code: str):
    """Decorator: require a specific permission code to access a view."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_superuser and not getattr(request.user, "agency_id", None):
                logger.warning("RBAC DENIED user=%s perm=%s reason=no_agency", request.user.pk, code)
                return HttpResponseForbidden("Acces refuse : aucune agence associee.")
            if not has_perm(request.user, code):
                logger.warning(
                    "RBAC DENIED user=%s role=%s perm=%s",
                    request.user.pk, getattr(request.user, "role", "?"), code,
                )
                return HttpResponseForbidden(f"Acces refuse : permission {code} requise.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
