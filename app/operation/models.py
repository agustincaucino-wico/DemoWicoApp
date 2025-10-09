from django.db import models
from accounts.models import Plates, Account
from stations.models import Station
from users.models import CustomUser


class PaymentMethod(models.Model):
    """
    Simple catalog for storing the available payment mechanisms
    that can be used when loading fuel.
    """

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class FuelLoadOperation(models.Model):
    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_NO_BALANCE = "no_balance"
    STATUS_CANCELED = "canceled"
    STATUS_TIMED_OUT = "timed_out"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_IN_PROGRESS, "En progreso"),
        (STATUS_COMPLETED, "Completada"),
        (STATUS_NO_BALANCE, "Sin saldo"),
        (STATUS_CANCELED, "Cancelada"),
        (STATUS_TIMED_OUT, "Expirada"),
    ]

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="fuel_operations",
        null=True,
        blank=True,
    )
    plate = models.ForeignKey(Plates, on_delete=models.CASCADE)
    attendant = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="attended_operations",
        null=True,
        blank=True,
    )
    station = models.ForeignKey(Station, on_delete=models.CASCADE)
    initial_amount = models.DecimalField(max_digits=12, decimal_places=2)
    final_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    timestamp_started = models.DateTimeField(auto_now_add=True)
    timestamp_atended = models.DateTimeField(null=True, blank=True)
    timestamp_finished = models.DateTimeField(null=True, blank=True)
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        ordering = ("-timestamp_started",)

    def __str__(self):
        return f"{self.final_amount} at {self.station} [{self.get_status_display()}]"
