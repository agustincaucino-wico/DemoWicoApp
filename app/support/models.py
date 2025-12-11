from django.db import models
from users.models import CustomUser


class FleetContactRequest(models.Model):
    """
    Model for fleet management contact requests.
    Any authenticated user can create a request.
    Only managers (Gestores) can view all requests.
    """

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("contacted", "Contactado"),
        ("converted", "Convertido"),
        ("rejected", "Rechazado"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="fleet_contact_requests",
        help_text="Usuario que solicita contacto",
    )
    phone_number = models.CharField(
        max_length=20, help_text="Número de teléfono de contacto"
    )
    contact_time = models.CharField(
        max_length=100, help_text="Horario preferido de contacto"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Estado de la solicitud",
    )
    notes = models.TextField(
        blank=True, null=True, help_text="Notas internas del gestor"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Solicitud de contacto - Flotas"
        verbose_name_plural = "Solicitudes de contacto - Flotas"

    def __str__(self):
        return f"Solicitud #{self.id} - {self.user.email} - {self.get_status_display()}"


class ErrorReport(models.Model):
    ERROR_CATEGORIES = [
        ("login", "Inicio de sesión"),
        ("balance", "Saldo y pagos"),
        ("fuel_load", "Carga de combustible"),
        ("transactions", "Movimientos"),
        ("other", "Otro problema"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("in_progress", "En progreso"),
        ("resolved", "Resuelto"),
        ("closed", "Cerrado"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="error_reports",
        help_text="Usuario que reporta el error",
    )
    category = models.CharField(
        max_length=20,
        choices=ERROR_CATEGORIES,
        help_text="Categoría del error reportado",
    )
    description = models.TextField(
        max_length=500, help_text="Descripción detallada del problema"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Estado del reporte",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        user_email = self.user.email if self.user else "Usuario eliminado"
        return f"Reporte #{self.id} - {self.get_category_display()} - {user_email}"
