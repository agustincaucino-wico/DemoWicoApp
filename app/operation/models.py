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
    WAITING_CANCELED = "waiting_canceled"
    CANCELED_BY_ATENDEE = "canceled_by_attendee"
    CANCELED_BY_USER = "canceled_by_user"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_IN_PROGRESS, "En progreso"),
        (STATUS_COMPLETED, "Completada"),
        (STATUS_NO_BALANCE, "Sin saldo"),
        (WAITING_CANCELED, "Espera cancelada por el usuario"),
        (CANCELED_BY_ATENDEE, "Cancelada por el playero"),
        (CANCELED_BY_USER, "Cancelada por el usuario"),
    ]

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="fuel_operations",
        null=True,
        blank=True,
    )
    plate = models.ForeignKey(Plates, on_delete=models.CASCADE, null=True, blank=True)
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
    fill_full_tank = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    timestamp_started = models.DateTimeField(auto_now_add=True)
    timestamp_atended = models.DateTimeField(null=True, blank=True)
    timestamp_finished = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(null=True, blank=True)
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        ordering = ("-timestamp_started",)

    def __str__(self):
        return f"{self.final_amount} at {self.station} [{self.get_status_display()}]"


class Transfer(models.Model):
    source_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transfers_sent"
    )
    destination_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transfers_received"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        return f"${self.amount} from {self.source_account.user.email} to {self.destination_account.user.email}"


# class AddFunds(models.Model):
#     account = models.ForeignKey(Account, on_delete=models.CASCADE)
#     timestamp = models.DateTimeField(auto_now_add=True)
#     amount = models.DecimalField(max_digits=12, decimal_places=2)
#     payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)

#     def __str__(self):
#         return f"Add {self.amount} to {self.account} via {self.payment_method}"
