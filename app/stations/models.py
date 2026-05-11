from django.conf import settings
from django.db import models


class FuelType(models.Model):
    """Tipo de combustible (ej: Nafta Super, Diesel, GNC)."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    biofuel_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Porcentaje de biocombustible",
        help_text="Porcentaje de biocombustible contenido en este combustible (ej: 7.5 para 7.5%)",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Tipo de combustible"
        verbose_name_plural = "Tipos de combustible"

    def __str__(self):
        return self.name


class FuelTypePrice(models.Model):
    """Precio histórico de un tipo de combustible por empresa y fecha."""

    fuel_type = models.ForeignKey(
        FuelType, on_delete=models.CASCADE, related_name="prices"
    )
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="fuel_prices"
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()

    class Meta:
        ordering = ["-effective_date"]
        verbose_name = "Precio de combustible"
        verbose_name_plural = "Precios de combustible"

    def __str__(self):
        return (
            f"{self.fuel_type.name} - {self.company.name}: "
            f"${self.price} ({self.effective_date})"
        )


class Station(models.Model):
    EXPENDIO_CHOICES = [
        ("cordoba", "Exclusiva Biocombustibles Córdoba"),
    ]

    name = models.CharField(max_length=255)
    province = models.ForeignKey("locations.Province", on_delete=models.CASCADE)
    city = models.ForeignKey("locations.City", on_delete=models.CASCADE)
    street = models.CharField(max_length=255, null=True, blank=True)
    street_number = models.CharField(max_length=10, null=True, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    expendio = models.CharField(
        max_length=100, null=True, blank=True, choices=EXPENDIO_CHOICES
    )

    class Meta:
        verbose_name = "Station"
        verbose_name_plural = "Stations"
        unique_together = (("name", "street", "street_number", "city"),)

    def __str__(self) -> str:
        return f"{self.name} - {self.street} {self.street_number}"


class StationAttendantAssignment(models.Model):
    attendant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Station attendant assignment"
        verbose_name_plural = "Station attendant assignments"
        ordering = ("-start_date", "attendant__id")

    def __str__(self) -> str:
        return f"{self.attendant} -> {self.station} ({self.start_date})"
