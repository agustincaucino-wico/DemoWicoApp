from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import ErrorReport


class ErrorReportSerializer(serializers.ModelSerializer):
    """
    Serializer para reportes de errores.

    Campos:
    - id: ID único del reporte (auto-generado)
    - user: ID del usuario que creó el reporte (asignado automáticamente)
    - user_email: Email del usuario (solo lectura)
    - category: Categoría del error (login, balance, fuel_load, transactions, other)
    - category_display: Nombre legible de la categoría (solo lectura)
    - description: Descripción detallada del problema (max 500 caracteres)
    - status: Estado del reporte (pending, in_progress, resolved, closed)
    - status_display: Nombre legible del estado (solo lectura)
    - created_at: Fecha de creación (auto-generado)
    - updated_at: Fecha de última actualización (auto-generado)
    """

    user_email = serializers.EmailField(source="user.email", read_only=True)

    @extend_schema_field(serializers.CharField)
    def get_category_display(self, obj):
        return obj.get_category_display()

    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )

    @extend_schema_field(serializers.CharField)
    def get_status_display(self, obj):
        return obj.get_status_display()

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ErrorReport
        fields = [
            "id",
            "user",
            "user_email",
            "category",
            "category_display",
            "description",
            "status",
            "status_display",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user"]

    def validate_description(self, value):
        """Validar que la descripción no esté vacía y tenga un mínimo de caracteres."""
        if not value or not value.strip():
            raise serializers.ValidationError("La descripción no puede estar vacía.")
        if len(value) > 500:
            raise serializers.ValidationError(
                "La descripción no puede tener más de 500 caracteres."
            )
        return value.strip()

    def create(self, validated_data):
        """Asignar automáticamente el usuario autenticado al crear el reporte."""
        request = self.context.get("request")
        if request and request.user:
            validated_data["user"] = request.user
        return super().create(validated_data)
