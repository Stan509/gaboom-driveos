from django.shortcuts import redirect
from django.utils import translation
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.translation import gettext as _
from core.services_language import language_detector


@require_POST
def set_language(request):
    """
    Vue simple pour changer la langue manuellement.
    """
    language = request.POST.get('language')
    
    # Langues supportées
    supported_languages = ['fr', 'en', 'es', 'ht']
    
    if language in supported_languages:
        # Activer la langue
        translation.activate(language)
        request.LANGUAGE_CODE = language
        
        # Sauvegarder en session
        request.session['django_language'] = language
        request.session.modified = True
        
        # Enregistrer la préférence manuelle
        try:
            from core.models_language import UserLanguagePreference
            UserLanguagePreference.objects.create(
                user=request.user if request.user.is_authenticated else None,
                agency=getattr(request.user, 'agency', None) if request.user.is_authenticated else None,
                session_key=request.session.session_key if hasattr(request, 'session') else None,
                ip_address=language_detector._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                language=language,
                source='manual',
                confidence=1.0
            )
        except Exception:
            pass  # Ne pas échouer si l'enregistrement ne fonctionne pas
        
        # Message de succès
        messages.success(request, _('Langue changée avec succès'))
    
    # Rediriger vers la page précédente
    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/'))
    return redirect(next_url)
