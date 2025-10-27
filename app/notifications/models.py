from django.db import models
from django.utils import timezone
from users.models import CustomUser


class Notification(models.Model):
    """
    Model to store user notifications for various events in the system.
    """

    NOTIFICATION_TYPES = [
        ("info", "Información"),
        ("success", "Éxito"),
        ("warning", "Advertencia"),
        ("error", "Error"),
        ("fuel", "Combustible"),
        ("account", "Cuenta"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Usuario",
    )
    title = models.CharField(max_length=255, verbose_name="Título")
    message = models.TextField(verbose_name="Mensaje")
    type = models.CharField(
        max_length=20, choices=NOTIFICATION_TYPES, default="info", verbose_name="Tipo"
    )
    is_read = models.BooleanField(default=False, verbose_name="Leída")
    action_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="URL de acción",
        help_text="URL opcional para navegar cuando se toca la notificación",
    )
    created_at = models.DateTimeField(
        default=timezone.now, verbose_name="Fecha de creación"
    )
    read_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha de lectura"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.email}"

    def mark_as_read(self):
        """Mark the notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    @classmethod
    def create_notification(
        cls, user, title, message, notification_type="info", action_url=None
    ):
        """
        Helper method to create a notification

        Args:
            user: CustomUser instance
            title: Notification title
            message: Notification message
            notification_type: Type of notification (info, success, warning, error, fuel, account)
            action_url: Optional URL to navigate to when notification is tapped

        Returns:
            Notification instance
        """
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            type=notification_type,
            action_url=action_url,
        )

    @classmethod
    def get_unread_count(cls, user):
        """Get the count of unread notifications for a user"""
        return cls.objects.filter(user=user, is_read=False).count()


class NotificationPreference(models.Model):
    """
    Model to store user notification preferences.
    """

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name="Usuario",
    )
    push_enabled = models.BooleanField(
        default=True, verbose_name="Notificaciones push habilitadas"
    )
    email_enabled = models.BooleanField(
        default=True, verbose_name="Notificaciones por email habilitadas"
    )
    fuel_load_notifications = models.BooleanField(
        default=True, verbose_name="Notificaciones de carga de combustible"
    )
    account_notifications = models.BooleanField(
        default=True, verbose_name="Notificaciones de cuenta"
    )
    balance_notifications = models.BooleanField(
        default=True, verbose_name="Notificaciones de saldo"
    )
    system_notifications = models.BooleanField(
        default=True, verbose_name="Notificaciones del sistema"
    )
    created_at = models.DateTimeField(
        default=timezone.now, verbose_name="Fecha de creación"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Última actualización"
    )

    class Meta:
        verbose_name = "Preferencia de notificación"
        verbose_name_plural = "Preferencias de notificación"

    def __str__(self):
        return f"Preferencias de {self.user.email}"
