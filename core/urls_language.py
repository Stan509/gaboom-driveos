from django.urls import path, include
from . import views_language, views_simple

app_name = 'core'

urlpatterns = [
    path('language/stats/', views_language.language_detection_stats, name='language_stats'),
    path('language/override/', views_language.override_language, name='override_language'),
    path('language/system-stats/', views_language.system_language_stats, name='system_language_stats'),
    path('set-language/', views_simple.set_language, name='set_language'),
    # Include master reset URLs
    path('', include('core.urls_master_reset')),
]
