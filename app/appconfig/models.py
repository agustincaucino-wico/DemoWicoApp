from django.db import models


class AppConfig(models.Model):
    """
    Singleton model for app-wide configuration.
    Only one instance should exist.
    """

    maintenance_mode = models.BooleanField(
        default=False,
        verbose_name="Modo mantenimiento",
        help_text="Activar para mostrar pantalla de mantenimiento en la app",
    )
    recharge_cbu = models.CharField(
        max_length=22,
        blank=True,
        verbose_name="CBU para Recargas",
        help_text="CBU de la cuenta bancaria para recibir transferencias de recarga de saldo",
    )
    support_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Teléfono de Soporte",
        help_text="Número de teléfono de WhatsApp para soporte (incluir código de país)",
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Última actualización"
    )

    class Meta:
        verbose_name = "Configuración de la App"
        verbose_name_plural = "Configuración de la App"

    def save(self, *args, **kwargs):
        # Ensure only one instance exists (singleton pattern)
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent deletion
        pass

    @classmethod
    def get_config(cls):
        """Get or create the singleton config instance."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def __str__(self):
        return "Configuración de la App"
