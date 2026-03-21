from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import translation
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from django.db import models
from django.conf import settings
from agencies.services import get_agency_access
from core.models_language import UserLanguagePreference, LanguagePattern
from core.services_language import language_detector


@login_required
def language_detection_stats(request):
    """
    Affiche les statistiques de détection de langue pour l'utilisateur.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return JsonResponse({'error': 'Non authentifié'}, status=401)
    
    # Récupérer les préférences récentes de l'utilisateur
    user_preferences = UserLanguagePreference.objects.filter(
        user=request.user
    ).order_by('-created_at')[:20]
    
    # Statistiques par langue
    language_stats = UserLanguagePreference.objects.filter(
        user=request.user
    ).values('language').annotate(
        count=models.Count('id'),
        avg_confidence=models.Avg('confidence')
    ).order_by('-count')
    
    # Préférence actuelle
    current_language = translation.get_language()
    
    # Détecter la langue actuelle du navigateur
    browser_language = language_detector._detect_from_browser_advanced(request)
    
    context = {
        'user_preferences': user_preferences,
        'language_stats': language_stats,
        'current_language': current_language,
        'browser_language': browser_language,
        'supported_languages': [
            {'code': code, 'name': name}
            for code, name in translation.get_languages()
        ],
    }
    
    return render(request, 'core/language_stats.html', context)


@require_POST
@login_required
def override_language(request):
    """
    Permet à un utilisateur de forcer temporairement une langue.
    """
    language = request.POST.get('language')
    
    if language not in [lang[0] for lang in settings.LANGUAGES]:
        return JsonResponse({'error': 'Langue non supportée'}, status=400)
    
    # Sauvegarder la préférence manuelle
    UserLanguagePreference.objects.create(
        user=request.user,
        agency=getattr(request.user, 'agency', None),
        language=language,
        source='manual',
        confidence=1.0,
        ip_address=language_detector._get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )
    
    # Mettre à jour la session
    request.session['django_language'] = language
    request.session.modified = True
    
    # Activer la langue
    translation.activate(language)
    
    return JsonResponse({
        'success': True,
        'language': language,
        'message': _('Langue mise à jour avec succès')
    })


@user_passes_test(lambda u: u.is_superuser)
def system_language_stats(request):
    """
    Statistiques linguistiques au niveau système (admin seulement).
    """
    # Statistiques globales
    global_stats = UserLanguagePreference.objects.values('language').annotate(
        count=models.Count('id'),
        unique_users=models.Count('user', distinct=True)
    ).order_by('-count')
    
    # Patterns les plus fiables
    reliable_patterns = LanguagePattern.objects.filter(
        confidence_score__gt=0.7
    ).order_by('-confidence_score')[:20]
    
    # Évolution sur les 30 derniers jours
    from django.utils import timezone
    from datetime import timedelta
    
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_trends = UserLanguagePreference.objects.filter(
        created_at__gte=thirty_days_ago
    ).extra(
        select={'day': 'date(created_at)'}
    ).values('day', 'language').annotate(
        count=models.Count('id')
    ).order_by('day', 'language')
    
    context = {
        'global_stats': global_stats,
        'reliable_patterns': reliable_patterns,
        'recent_trends': recent_trends,
    }
    
    return render(request, 'core/system_language_stats.html', context)
