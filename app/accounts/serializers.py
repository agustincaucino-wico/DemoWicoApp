from rest_framework import serializers
from .models import Account, Dependents, Plates, AuthorizedPlate
from .models import Company, CompanyAssignment


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = "__all__"


class DependentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dependents
        fields = "__all__"


class PlatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plates
        fields = "__all__"

    def validate_plate_number(self, value):
        """Validar que la patente sea única globalmente para patentes activas"""
        if value:
            # Normalizar la patente (convertir a mayúsculas y quitar espacios)
            normalized_plate = value.upper().strip()

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

    class Meta:
        model = Account
        fields = ["balance"]

    def validate_balance(self, value):
        """Validar que el balance sea un valor positivo o cero"""
        if value < 0:
            raise serializers.ValidationError("El balance no puede ser negativo")
        return value
