from django.db import models


class BonificationTier(models.Model):
    """
    Tramo de bonificación mayorista.
    El monto mínimo en pesos se calcula en tiempo real: min_liters × fuel_price.
    """

    min_liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Litros mínimos",
        help_text="Cantidad mínima de litros para acceder a este tramo.",
    )
    bonus_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Bonificación (%)",
        help_text="Porcentaje de bonificación aplicado sobre el monto recargado.",
    )
    color_intensity = models.FloatField(
        default=1.0,
        verbose_name="Intensidad de color",
        help_text="Valor entre 0 y 1 para degradado visual (1 = más oscuro).",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
        help_text="Orden de visualización (menor número = primero).",
    )

    class Meta:
        verbose_name = "Tramo de bonificación"
        verbose_name_plural = "Tramos de bonificación"
        ordering = ["order", "min_liters"]

    def __str__(self):
        return f"{self.min_liters} L → {self.bonus_percent}%"


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
    fuel_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio de Combustible de Referencia",
        help_text="Precio de referencia del combustible.",
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
