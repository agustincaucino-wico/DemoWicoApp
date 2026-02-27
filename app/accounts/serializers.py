from decimal import Decimal
from rest_framework import serializers
from .models import Account, Dependents, Plates, AuthorizedPlate
from .models import Company, CompanyAssignment


class AccountSerializer(serializers.ModelSerializer):
    deactivated_by_email = serializers.EmailField(
        source="deactivated_by.email", read_only=True
    )

    class Meta:
        model = Account
        fields = "__all__"
        read_only_fields = (
            "balance",
            "user",
            "account_type",
            "verification_status",
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deactivation_reason",
        )


class DependentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dependents
        fields = "__all__"


class PlatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plates
        fields = "__all__"

    def validate_plate_number(self, value):
        """Validar formato y que la patente sea única globalmente para patentes activas"""
        import re

        if value:
            # Normalizar la patente (convertir a mayúsculas y quitar espacios)
            normalized_plate = value.upper().strip()

            # Validar formato de patente argentina
            old_format = re.match(
                r"^[A-Z]{3}\d{3}$", normalized_plate
            )  # ABC123 (autos viejos)
            new_format = re.match(
                r"^[A-Z]{2}\d{3}[A-Z]{2}$", normalized_plate
            )  # AB123CD (autos nuevos)
            moto_format = re.match(
                r"^[A-Z]\d{3}[A-Z]{3}$", normalized_plate
            )  # A123BCD (motos)

            if not (old_format or new_format or moto_format):
                raise serializers.ValidationError(
                    "El formato de patente no es válido. Usa el formato ABC123, AB123CD o A123BCD"
                )

            existing_plates = Plates.objects.filter(
                plate_number=normalized_plate, end_date__isnull=True
            )

            # Si estamos editando una patente existente, excluirla de la validación
            if self.instance:
                existing_plates = existing_plates.exclude(pk=self.instance.pk)

            if existing_plates.exists():
                raise serializers.ValidationError(
                    f"La patente '{normalized_plate}' ya está registrada en el sistema"
                )

            return normalized_plate

        return value

    def validate(self, attrs):
        holder_account = attrs.get("holder_account")

        # Validar que el usuario solo pueda crear patentes para sus propias cuentas titulares
        request = self.context.get("request")
        if request and holder_account:
            user_accounts = request.user.account_set.filter(account_type="holder")
            if holder_account not in user_accounts:
                raise serializers.ValidationError(
                    "Solo puedes crear patentes para tus propias cuentas titulares"
                )

        return attrs


class PlatesUpdateSerializer(serializers.ModelSerializer):
    """Serializer específico para actualizar solo marca y modelo de una patente"""

    class Meta:
        model = Plates
        fields = ["brand", "model"]


class AuthorizedPlateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthorizedPlate
        fields = "__all__"

    def validate(self, attrs):
        plate = attrs.get("plate")
        holder_account = plate.holder_account if plate else None
        dependent_account = attrs.get("dependent_account")

        # Validar que el usuario solo pueda autorizar patentes de sus propias cuentas titulares
        request = self.context.get("request")
        if request and holder_account:
            user_accounts = request.user.account_set.filter(account_type="holder")
            if holder_account not in user_accounts:
                raise serializers.ValidationError(
                    "Solo puedes autorizar patentes de tus propias cuentas titulares"
                )

        # Validar que la cuenta a autorizar sea un dependiente de la holder_account
        if dependent_account and holder_account:
            if not Dependents.objects.filter(
                holder_account=holder_account,
                dependent_account=dependent_account,
                end_date__isnull=True,
            ).exists():
                raise serializers.ValidationError(
                    "La cuenta a autorizar debe ser un adherente activo de la cuenta titular de la patente"
                )

        # Validar que no exista una relación activa entre la patente y el usuario
        if plate and dependent_account:
            # Excluir la instancia actual si estamos editando
            existing_authorization = AuthorizedPlate.objects.filter(
                plate=plate, dependent_account=dependent_account, end_date__isnull=True
            )

            if self.instance:
                existing_authorization = existing_authorization.exclude(
                    pk=self.instance.pk
                )

            if existing_authorization.exists():
                raise serializers.ValidationError(
                    "Ya existe una autorización activa de esta patente para este usuario"
                )

        return attrs


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = "__all__"


class CompanyAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyAssignment
        fields = "__all__"


class AddDependentSerializer(serializers.Serializer):
    holder_account_id = serializers.IntegerField(
        help_text="ID of the holder account to add the dependent to"
    )
    dependent_email = serializers.EmailField(
        help_text="Email of the user to be added as a dependent"
    )


class AccountBalanceUpdateSerializer(serializers.ModelSerializer):
    """Serializer específico para actualizar solo el balance de una cuenta"""

    comments = serializers.CharField(
        required=False, allow_blank=True, help_text="Comentarios adicionales (opcional)"
    )

    class Meta:
        model = Account
        fields = ["balance", "comments"]

    def validate_balance(self, value):
        """Validar que el balance sea un valor positivo o cero y no exceda el límite"""
        if value < 0:
            raise serializers.ValidationError("El balance no puede ser negativo")
        # Límite: 13 dígitos enteros + 2 decimales = 9,999,999,999,999.99
        max_value = Decimal("9999999999999.99")
        if value > max_value:
            raise serializers.ValidationError(
                f"El balance no puede exceder {max_value:,.2f}"
            )
        return value
