from django.db import models
from django.utils import timezone
from agencies.models import Agency


class UserLanguagePreference(models.Model):
    """
    Stocke les préférences linguistiques des utilisateurs pour un apprentissage automatique.
    """
    
    LANGUAGE_CHOICES = [
        ("fr", "Français"),
        ("en", "English"),
        ("es", "Español"),
        ("ht", "Kreyòl"),
    ]
    
    SOURCE_TYPES = [
        ("browser", "Navigateur"),
        ("session", "Session"),
        ("manual", "Manuel"),
        ("detected", "Détecté automatiquement"),
    ]
    
    user = models.ForeignKey(
        "core.User", 
        on_delete=models.CASCADE, 
        related_name="language_preferences",
        null=True, 
        blank=True
    )
    agency = models.ForeignKey(
        Agency, 
        on_delete=models.CASCADE, 
        related_name="language_preferences",
        null=True, 
        blank=True
    )
    session_key = models.CharField(max_length=40, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_TYPES, default="detected")
    confidence = models.FloatField(default=1.0, help_text="Niveau de confiance de 0 à 1")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["agency", "-created_at"]),
            models.Index(fields=["session_key", "-created_at"]),
            models.Index(fields=["ip_address", "-created_at"]),
            models.Index(fields=["language", "-created_at"]),
        ]
        verbose_name = "Préférence linguistique"
        verbose_name_plural = "Préférences linguistiques"
    
    def __str__(self):
        identifier = self.user.username if self.user else (self.agency.name if self.agency else self.session_key[:8])
        return f"{identifier} → {self.get_language_display()}"


class LanguagePattern(models.Model):
    """
    Analyse les patterns linguistiques pour améliorer la détection automatique.
    """
    
    pattern_type = models.CharField(max_length=50, help_text="Type de pattern (ex: 'browser_lang', 'time_based', 'geo_based')")
    pattern_data = models.JSONField(help_text="Données du pattern")
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    confidence_score = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-confidence_score", "-success_count"]
        verbose_name = "Pattern linguistique"
        verbose_name_plural = "Patterns linguistiques"
    
    @property
    def success_rate(self):
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
