from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import ErrorReport, FleetContactRequest


class FleetContactRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for fleet contact requests.

    Fields:
    - id: Unique request ID (auto-generated)
    - user: User ID who created the request (assigned automatically on create)
    - user_email: User's email (read-only)
    - user_full_name: User's full name (read-only)
    - phone_number: Contact phone number (required)
    - contact_time: Preferred contact hours (required)
    - status: Request status (pending, contacted, converted, rejected)
    - status_display: Human-readable status (read-only)
    - notes: Internal manager notes (only visible to managers)
    - created_at: Creation date (auto-generated)
    - updated_at: Last update date (auto-generated)
    """

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField(read_only=True)

    @extend_schema_field(serializers.CharField)
    def get_user_full_name(self, obj):
        if obj.user.first_name and obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return obj.user.email

    @extend_schema_field(serializers.CharField)
    def get_status_display(self, obj):
        return obj.get_status_display()

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = FleetContactRequest
        fields = [
            "id",
            "user",
            "user_email",
            "user_full_name",
            "phone_number",
            "contact_time",
            "status",
            "status_display",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def create(self, validated_data):
        # Automatically assign the authenticated user
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


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
