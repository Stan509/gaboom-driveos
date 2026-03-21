import re
import json
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import translation
from django.db.models import Count, Avg, Q
from django.http import HttpRequest
from agencies.models import Agency
from core.models import User
from .models_language import UserLanguagePreference, LanguagePattern


class SmartLanguageDetector:
    """
    Service intelligent pour détecter automatiquement la langue préférée de l'utilisateur
    en se basant sur ses habitudes et patterns d'utilisation.
    """
    
    def __init__(self):
        self.supported_languages = [lang[0] for lang in settings.LANGUAGES]
        self.default_language = settings.LANGUAGE_CODE
    
    def detect_language(self, request: HttpRequest) -> str:
        """
        Détecte la langue la plus appropriée pour l'utilisateur.
        """
        # 1. Vérifier si l'utilisateur a une session active avec une langue
        if hasattr(request, 'session') and request.session.get('django_language'):
            session_lang = request.session.get('django_language')
            if session_lang in self.supported_languages:
                self._record_preference(request, session_lang, 'session', confidence=0.9)
                return session_lang
        
        # 2. Vérifier les préférences utilisateur enregistrées
        user_language = self._get_user_preference(request)
        if user_language:
            self._record_preference(request, user_language, 'detected', confidence=0.8)
            return user_language
        
        # 3. Analyser les patterns de l'agence
        agency_language = self._get_agency_preference(request)
        if agency_language:
            self._record_preference(request, agency_language, 'detected', confidence=0.7)
            return agency_language
        
        # 4. Détecter depuis le navigateur avec analyse avancée
        browser_language = self._detect_from_browser_advanced(request)
        if browser_language:
            self._record_preference(request, browser_language, 'browser', confidence=0.6)
            return browser_language
        
        # 5. Retourner la langue par défaut
        return self.default_language
    
    def _get_user_preference(self, request: HttpRequest) -> str:
        """
        Récupère la langue préférée de l'utilisateur basée sur son historique.
        """
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None
        
        # Analyser les 30 derniers jours de préférences
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        preferences = UserLanguagePreference.objects.filter(
            user=request.user,
            created_at__gte=thirty_days_ago
        ).values('language').annotate(
            count=Count('id'),
            avg_confidence=Avg('confidence')
        ).order_by('-count', '-avg_confidence')
        
        if preferences:
            best_match = preferences.first()
            return best_match['language']
        
        return None
    
    def _get_agency_preference(self, request: HttpRequest) -> str:
        """
        Récupère la langue la plus utilisée dans l'agence.
        """
        try:
            if hasattr(request, 'user') and hasattr(request.user, 'agency') and request.user.agency:
                agency = request.user.agency
            else:
                # Essayer de détecter l'agence depuis le domaine ou autre
                agency = self._detect_agency_from_request(request)
            
            if not agency:
                return None
            
            # Analyser les préférences de l'agence
            preferences = UserLanguagePreference.objects.filter(
                agency=agency,
                created_at__gte=datetime.now() - timedelta(days=60)
            ).values('language').annotate(
                count=Count('id')
            ).order_by('-count')
            
            if preferences:
                return preferences.first()['language']
                
        except Exception:
            pass
        
        return None
    
    def _detect_agency_from_request(self, request: HttpRequest) -> Agency:
        """
        Détecte l'agence depuis la requête (domaine, sous-domaine, etc.).
        """
        # Logique de détection d'agence depuis le domaine/URL
        host = request.get_host()
        
        # Si c'est un sous-domaine qui correspond à une agence
        subdomain = host.split('.')[0] if '.' in host else None
        if subdomain:
            try:
                return Agency.objects.filter(slug=subdomain).first()
            except Exception:
                pass
        
        return None
    
    def _detect_from_browser_advanced(self, request: HttpRequest) -> str:
        """
        Détection avancée depuis l'en-tête Accept-Language avec patterns.
        """
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if not accept_language:
            return None
        
        # Parser l'en-tête
        languages = self._parse_accept_language(accept_language)
        
        # Analyser chaque langue avec les patterns connus
        for lang_code, quality in languages:
            # Correspondance exacte
            if lang_code in self.supported_languages:
                # Vérifier les patterns pour cette langue
                if self._validate_language_pattern(request, lang_code):
                    return lang_code
            
            # Correspondance partielle (ex: 'en-US' -> 'en')
            base_lang = lang_code.split('-')[0].lower()
            if base_lang in self.supported_languages:
                if self._validate_language_pattern(request, base_lang):
                    return base_lang
        
        return None
    
    def _parse_accept_language(self, accept_language: str) -> list:
        """
        Parse l'en-tête Accept-Language avec gestion des qualités.
        """
        languages = []
        pattern = r'([a-zA-Z]{1,8}(?:-[a-zA-Z0-9]{1,8})?)(?:;q=([0-9.]+))?'
        matches = re.findall(pattern, accept_language)
        
        for lang, quality in matches:
            q = float(quality) if quality else 1.0
            languages.append((lang.lower(), q))
        
        # Trier par qualité
        languages.sort(key=lambda x: x[1], reverse=True)
        return languages
    
    def _validate_language_pattern(self, request: HttpRequest, language: str) -> bool:
        """
        Valide si la langue détectée correspond aux patterns connus.
        """
        # Vérifier les patterns enregistrés pour cette combinaison
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        ip_address = self._get_client_ip(request)
        
        # Pattern basé sur le User-Agent
        pattern_key = f"ua_lang_{hash(user_agent) % 1000}"
        pattern = LanguagePattern.objects.filter(
            pattern_type=pattern_key,
            pattern_data__language=language
        ).first()
        
        if pattern and pattern.confidence_score > 0.7:
            return True
        
        return True  # Par défaut, on fait confiance
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """
        Récupère l'adresse IP réelle du client.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _record_preference(self, request: HttpRequest, language: str, source: str, confidence: float = 1.0):
        """
        Enregistre la préférence linguistique pour l'apprentissage futur.
        """
        try:
            # Créer l'enregistrement de préférence
            preference = UserLanguagePreference.objects.create(
                user=request.user if request.user.is_authenticated else None,
                agency=getattr(request.user, 'agency', None) if request.user.is_authenticated else self._detect_agency_from_request(request),
                session_key=request.session.session_key if hasattr(request, 'session') else None,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                language=language,
                source=source,
                confidence=confidence
            )
            
            # Mettre à jour les patterns
            self._update_patterns(request, language, success=True)
            
        except Exception:
            pass  # Ne pas échouer si l'enregistrement ne fonctionne pas
    
    def _update_patterns(self, request: HttpRequest, language: str, success: bool):
        """
        Met à jour les patterns d'apprentissage.
        """
        try:
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            pattern_key = f"ua_lang_{hash(user_agent) % 1000}"
            
            pattern, created = LanguagePattern.objects.get_or_create(
                pattern_type=pattern_key,
                pattern_data={'language': language, 'ua_sample': user_agent[:100]},
                defaults={'success_count': 1, 'failure_count': 0, 'confidence_score': 0.5}
            )
            
            if not created:
                if success:
                    pattern.success_count += 1
                else:
                    pattern.failure_count += 1
                
                # Calculer le score de confiance
                total = pattern.success_count + pattern.failure_count
                pattern.confidence_score = pattern.success_count / total if total > 0 else 0.0
                pattern.save()
                
        except Exception:
            pass


# Instance globale du détecteur
language_detector = SmartLanguageDetector()
