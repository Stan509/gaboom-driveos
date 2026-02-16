from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        import core.signals  # noqa: F401 — register post_save signals
        import core.models_platform  # noqa: F401 — PlatformSettings singleton
        import core.models_paypal_event  # noqa: F401 — PayPalEvent log
        import core.models_paypal_subscription  # noqa: F401
        import core.models_admin_alert  # noqa: F401
