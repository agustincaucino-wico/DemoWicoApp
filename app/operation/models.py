from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from accounts.models import Plates, Account
from stations.models import Station
from users.models import CustomUser


def validate_file_size(file):
    """Validate that file size is not greater than 5MB"""
    max_size_mb = 5
    if file.size > max_size_mb * 1024 * 1024:
        file_size_mb = file.size / (1024 * 1024)
        raise ValidationError(
            f"El archivo es demasiado grande ({file_size_mb:.2f}MB). "
            f"El tamaño máximo permitido es {max_size_mb}MB. "
        )


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
    initial_amount = models.DecimalField(max_digits=15, decimal_places=2)
    final_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
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
    fuel_type = models.ForeignKey(
        "stations.FuelType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fuel_operations",
    )
    odometer_km = models.PositiveIntegerField(null=True, blank=True)
    quantity_liters = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
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
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        return f"${self.amount} from {self.source_account.user.email} to {self.destination_account.user.email}"


class ModifyFunds(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    gestor = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, null=True, blank=True
    )
    comments = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        means = (
            f" via {self.payment_method.name}"
            if self.payment_method
            else f" by {self.gestor.email}"
        )
        if self.amount >= 0:
            return f"Added ${self.amount} to {self.account.user.email}{means}"
        else:
            return f"Removed ${-self.amount} from {self.account.user.email}{means}"


class BalanceRechargeRequest(models.Model):
    """
    Model for tracking balance recharge requests via bank transfer.
    Users submit proof of transfer and wait for admin/gestor approval.
    """

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_APPROVED, "Aprobada"),
        (STATUS_REJECTED, "Rechazada"),
    ]

    # Request information
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="recharge_requests",
        help_text="Account to be recharged",
    )
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="recharge_requests",
        help_text="User who requested the recharge",
    )
    amount = models.DecimalField(
        max_digits=15, decimal_places=2, help_text="Amount to be added to the account"
    )
    transfer_proof = models.FileField(
        upload_to="recharge_proofs/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "jpg", "jpeg", "png"],
                message="Solo se permiten archivos PDF, JPG o PNG",
            ),
            validate_file_size,
        ],
        help_text="Proof of bank transfer (PDF, JPG, PNG - Max 5MB)",
    )
    comments = models.TextField(blank=True, help_text="Optional comments from the user")

    # Status tracking
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )

    # Review information
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_recharge_requests",
        help_text="Gestor/Admin who reviewed the request",
    )
    reviewed_at = models.DateTimeField(
        null=True, blank=True, help_text="When the request was reviewed"
    )
    review_comments = models.TextField(
        blank=True, help_text="Comments from the reviewer"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        verbose_name = "Solicitud de Recarga"
        verbose_name_plural = "Solicitudes de Recarga"

    def __str__(self):
        return f"Recarga de ${self.amount} - {self.account.user.email} ({self.get_status_display()})"

    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING

    @property
    def is_approved(self):
        return self.status == self.STATUS_APPROVED

    @property
    def is_rejected(self):
        return self.status == self.STATUS_REJECTED
