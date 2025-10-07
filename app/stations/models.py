from django.conf import settings
from django.db import models


class Station(models.Model):
    name = models.CharField(max_length=255)
    province = models.ForeignKey("locations.Province", on_delete=models.CASCADE)
    city = models.ForeignKey("locations.City", on_delete=models.CASCADE)
    street = models.CharField(max_length=255, null=True, blank=True)
    street_number = models.CharField(max_length=10, null=True, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

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
        constraints = [
            models.UniqueConstraint(
                fields=["attendant", "station", "start_date"],
                name="unique_assignment_per_start_date",
            )
        ]

    def __str__(self) -> str:
        return f"{self.attendant} -> {self.station} ({self.start_date})"
