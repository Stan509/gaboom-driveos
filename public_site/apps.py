from django.apps import AppConfig


class PublicSiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "public_site"

    def ready(self):
        import public_site.signals  # noqa: F401
