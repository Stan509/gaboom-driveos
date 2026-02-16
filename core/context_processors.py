from agencies.services import get_agency_access
from core.permissions import get_effective_permissions


def user_permissions(request):
    """Inject user_perms set into every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"user_perms": set(), "plan_features": {}, "plan_code": None}
    perms = get_effective_permissions(request.user)
    agency = getattr(request.user, "agency", None)
    if not agency:
        return {"user_perms": perms, "plan_features": {}, "plan_code": None}
    access = get_agency_access(agency)
    return {"user_perms": perms, "plan_features": access.plan_features, "plan_code": access.plan_code}


# ── Theme defaults per preset ────────────────────────────────────────
_THEME_PRESETS = {
    "dark": {
        "bg": "#0F0F0F", "surface": "#1A1A1A", "accent": "#F5B400",
        "text": "#FFFFFF", "text_muted": "#999999",
        "sidebar_bg": "#141414", "sidebar_border": "#2A2A2A",
        "header_bg": "rgba(20,20,20,.95)", "header_border": "#2A2A2A",
        "card_border": "#2A2A2A", "hover_glow": "rgba(245,180,0,.12)",
        "nav_active_bg": "rgba(245,180,0,.10)", "nav_active_color": "#F5B400",
        "nav_active_bar": "#F5B400", "nav_hover_bg": "rgba(245,180,0,.05)",
        "btn_primary_bg": "#F5B400", "btn_primary_text": "#0F0F0F",
        "badge_bg": "#2A2A2A",
    },
    "gaboom": {
        "bg": "#F8F5FF", "surface": "#FFFFFF", "accent": "#6D28D9",
        "text": "#1E1B4B", "text_muted": "#6B7280",
        "sidebar_bg": "#FFFFFF", "sidebar_border": "#E5E7EB",
        "header_bg": "rgba(255,255,255,.95)", "header_border": "#E5E7EB",
        "card_border": "#E5E7EB", "hover_glow": "rgba(109,40,217,.08)",
        "nav_active_bg": "rgba(109,40,217,.08)", "nav_active_color": "#6D28D9",
        "nav_active_bar": "#6D28D9", "nav_hover_bg": "rgba(109,40,217,.04)",
        "btn_primary_bg": "#6D28D9", "btn_primary_text": "#FFFFFF",
        "badge_bg": "#F3F4F6",
    },
}


def dashboard_theme(request):
    """Inject dashboard theme variables into every template context."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {}
    agency = getattr(request.user, "agency", None)
    if not agency:
        return {}

    try:
        ts = agency.theme_settings
    except Exception:
        ts = None

    theme_choice = ts.theme_choice if ts else "dark"
    preset = _THEME_PRESETS.get(theme_choice, _THEME_PRESETS["dark"])

    # Allow custom overrides
    if ts and ts.primary_color:
        preset = {**preset, "accent": ts.primary_color, "nav_active_color": ts.primary_color,
                  "nav_active_bar": ts.primary_color, "btn_primary_bg": ts.primary_color}
    if ts and ts.secondary_color:
        preset = {**preset, "hover_glow": ts.secondary_color}

    radius = ts.border_radius if ts else 14
    animations = ts.enable_animations if ts else True
    glow = ts.enable_glow_effect if ts else True

    return {
        "dash_theme": theme_choice,
        "dash_colors": preset,
        "dash_radius": radius,
        "dash_animations": animations,
        "dash_glow": glow,
    }
