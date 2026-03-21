from django.conf import settings
from django.utils import translation
from django.http import HttpResponse
from django.middleware.locale import LocaleMiddleware
from django.utils.cache import patch_vary_headers
from .services_language import language_detector


class AutoLocaleMiddleware(LocaleMiddleware):
    """
    Middleware qui détecte automatiquement la langue préférée de l'utilisateur
    basée sur ses habitudes, patterns d'utilisation et préférences du navigateur.
    """
    
    def process_request(self, request):
        # Ne pas appliquer sur les URLs API ou admin
        if request.path_info.startswith('/api/') or request.path_info.startswith('/admin/'):
            return None
            
        # Priorité 1: Vérifier si l'utilisateur a une session active avec une langue (changement manuel)
        if hasattr(request, 'session') and request.session.get('django_language'):
            session_lang = request.session.get('django_language')
            # Langues supportées
            supported_languages = ['fr', 'en', 'es', 'ht']
            if session_lang in supported_languages:
                translation.activate(session_lang)
                request.LANGUAGE_CODE = session_lang
                return None  # Ne pas continuer avec la détection automatique
        
        # Priorité 2: Utiliser le détecteur intelligent de langue uniquement si pas de choix manuel
        language = language_detector.detect_language(request)
        
        # Activer la langue détectée
        translation.activate(language)
        request.LANGUAGE_CODE = language
        
        # Sauvegarder en session pour maintenir la cohérence
        if hasattr(request, 'session'):
            request.session['django_language'] = language
            request.session.modified = True
    
    def process_response(self, request, response):
        """
        Ajoute les en-têtes Vary pour indiquer que la réponse dépend de la langue.
        """
        if isinstance(response, HttpResponse):
            patch_vary_headers(response, ('Accept-Language',))
            response['Content-Language'] = translation.get_language()
        return response
