from django.db import models
from users.models import CustomUser


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
