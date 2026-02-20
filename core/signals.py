from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def notify_admin_on_new_user(sender, instance, created, **kwargs):
    """Send an email to ADMINS every time a new user signs up."""
    if not created:
        return

    subject = f"Nouvelle inscription : {instance.email or instance.username}"
    message = (
        "Un nouvel utilisateur s'est inscrit sur Gaboom DriveOS !\n\n"
        f"Email       : {instance.email}\n"
        f"Username    : {instance.username}\n"
        f"Nom complet : {instance.full_name or '—'}\n"
        f"Téléphone   : {instance.phone or '—'}\n"
    )
    if instance.agency_id:
        message += f"Agence      : {instance.agency} (ID {instance.agency_id})\n"
    message += (
        f"Rôle        : {instance.get_role_display()}\n"
        f"Date        : {instance.date_joined}\n"
        f"ID          : {instance.id}\n"
        f"Actif       : {instance.is_active}\n"
        f"Email vérifié : {instance.email_verified}\n"
    )

    try:
        if not settings.ADMINS:
            return
        admin_email = settings.ADMINS[0][1]
        from core.email import send_email
        send_email(
            to_email=admin_email,
            subject=subject,
            html_content=f"<pre>{message}</pre>",
        )
    except Exception:
        return
