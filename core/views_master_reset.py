from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.utils.http import urlencode

from agencies.models import Agency
from core.crypto import ensure_fernet_key
from core.models_platform import PlatformSettings
import secrets

User = get_user_model()

DEFAULT_MASTER_CODE = "GaboomMaster2024!"


def _get_master_code() -> str:
    ensure_fernet_key()
    ps = PlatformSettings.get()
    if not ps.master_code:
        ps.set_master_code(DEFAULT_MASTER_CODE)
        ps.save(update_fields=["master_code_encrypted"])
    return ps.master_code

def master_reset_view(request):
    """Allow superadmin to reset any agency password using master code."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?{urlencode({'next': request.get_full_path()})}")
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")

    if request.method == "POST":
        master_code_expected = _get_master_code()
        master_code = request.POST.get("master_code", "").strip()
        agency_name = request.POST.get("agency_name", "").strip()
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        # Verify master code
        if master_code != master_code_expected:
            messages.error(request, "Code master incorrect.")
            return redirect("/master-reset/")

        # Validate passwords
        if not new_password or len(new_password) < 8:
            messages.error(request, "Le mot de passe doit contenir au moins 8 caractères.")
            return redirect("/master-reset/")

        if new_password != confirm_password:
            messages.error(request, "Les mots de passe ne correspondent pas.")
            return redirect("/master-reset/")

        # Find agency
        try:
            agency = Agency.objects.get(name__iexact=agency_name)
        except Agency.DoesNotExist:
            messages.error(request, f"Aucune agence trouvée avec le nom '{agency_name}'.")
            return redirect("/master-reset/")

        # Find agency owner (user with role agency_owner in this agency)
        try:
            owner_user = User.objects.get(agency=agency, role='agency_owner')
        except User.DoesNotExist:
            messages.error(request, f"Aucun propriétaire trouvé pour l'agence '{agency_name}'.")
            return redirect("/master-reset/")

        # Reset password
        owner_user.set_password(new_password)
        owner_user.save()
        
        messages.success(request, f"Mot de passe réinitialisé avec succès pour l'agence '{agency.name}'. Le propriétaire ({owner_user.email}) peut maintenant se connecter avec le nouveau mot de passe.")
        return redirect("/master-reset/")

    return render(request, "core/master_reset.html")

def regenerate_master_code_view(request):
    """Regenerate the master code (for superadmin only)."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?{urlencode({'next': request.get_full_path()})}")
    if not request.user.is_superuser:
        return HttpResponseForbidden("Forbidden")

    ensure_fernet_key()
    ps = PlatformSettings.get()
    new_code = "Gaboom" + secrets.token_urlsafe(16)
    ps.set_master_code(new_code)
    ps.save(update_fields=["master_code_encrypted"])
    messages.success(request, f"Nouveau code master généré : {new_code}")
    return redirect("/master-reset/")
