from decimal import Decimal
from datetime import date
from rest_framework import serializers
from .models import Account, Dependents, Plates, AuthorizedPlate
from .models import Company, CompanyAssignment, Organism, AuthorizedEmail


class OrganismSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organism
        fields = "__all__"


class AccountSerializer(serializers.ModelSerializer):
    deactivated_by_email = serializers.EmailField(
        source="deactivated_by.email", read_only=True
    )
    company_name = serializers.CharField(
        source="company.name", read_only=True, allow_null=True
    )
    holder_account_id = serializers.SerializerMethodField()
    holder_account_name = serializers.SerializerMethodField()

    def get_holder_account_id(self, obj):
        dep = obj.dependents_as_dependent.filter(end_date__isnull=True).first()
        if dep is None:
            dep = obj.dependents_as_dependent.order_by('-end_date').first()
        return dep.holder_account_id if dep else None

    def get_holder_account_name(self, obj):
        dep = (
            obj.dependents_as_dependent.filter(end_date__isnull=True)
            .select_related("holder_account__user")
            .first()
        )
        if dep is None:
            dep = (
                obj.dependents_as_dependent.order_by('-end_date')
                .select_related("holder_account__user")
                .first()
            )
        if not dep:
            return None
        user = dep.holder_account.user
        if user:
            full = f"{user.first_name} {user.last_name}".strip()
            return full or user.email
        return f"Cuenta #{dep.holder_account_id}"

    class Meta:
        model = Account
        fields = "__all__"
        read_only_fields = (
            "balance",
            "user",
            "account_type",
            "display_type",
            "verification_status",
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deactivation_reason",
        )


class DependentsSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        source='dependent_account.user.email', read_only=True
    )
    dni = serializers.CharField(
        source='dependent_account.user.dni', read_only=True
    )
    dependent_user = serializers.SerializerMethodField()
    holder_email = serializers.EmailField(
        source='holder_account.user.email', read_only=True
    )

    def get_dependent_user(self, obj):
        user = getattr(getattr(obj.dependent_account, 'user', None), '__dict__', None)
        u = obj.dependent_account.user if obj.dependent_account else None
        if not u:
            return None
        return {
            'email': u.email,
            'dni': u.dni,
            'first_name': u.first_name or '',
            'last_name': u.last_name or '',
        }

    class Meta:
        model = Dependents
        fields = ['id', 'holder_account', 'dependent_account', 'start_date', 'end_date',
                  'email', 'dni', 'dependent_user', 'holder_email']


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
    organism_name = serializers.CharField(
        source="organism.name", read_only=True, allow_null=True
    )
    province_name = serializers.CharField(
        source="province.name", read_only=True, allow_null=True
    )

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "province",
            "province_name",
            "organism",
            "organism_name",
            "cuit",
            "billing_type",
            "tax_condition",
        ]


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


class AdminAccountCreateSerializer(serializers.ModelSerializer):
    """Serializer para que un admin cree una cuenta para un usuario."""

    holder_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(account_type="holder", is_active=True),
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = Account
        fields = [
            "user",
            "account_type",
            "balance",
            "display_type",
            "special",
            "unlimited_balance",
            "company",
            "holder_account",
        ]

    def validate_balance(self, value):
        if value < 0:
            raise serializers.ValidationError("El balance no puede ser negativo")
        return value

    def validate(self, attrs):
        account_type = attrs.get("account_type")
        holder_account = attrs.get("holder_account")
        user = attrs.get("user")

        if account_type == "holder" and user:
            if Account.objects.filter(user=user, account_type="holder", is_active=True).exists():
                raise serializers.ValidationError(
                    {"user": "Este usuario ya tiene una cuenta titular activa."}
                )

        if account_type == "dependent" and holder_account and user:
            already_exists = Dependents.objects.filter(
                holder_account=holder_account,
                dependent_account__user=user,
                end_date__isnull=True,
            ).exists()
            if already_exists:
                raise serializers.ValidationError(
                    {
                        "holder_account": "Este usuario ya tiene una cuenta adherente activa para esa cuenta titular."
                    }
                )

        return attrs

    def create(self, validated_data):
        holder_account = validated_data.pop("holder_account", None)
        account = super().create(validated_data)
        if holder_account is not None:
            Dependents.objects.create(
                holder_account=holder_account,
                dependent_account=account,
                start_date=date.today(),
            )
        return account


class AdminAccountUpdateSerializer(serializers.ModelSerializer):
    """Serializer para que un admin modifique parámetros de una cuenta."""

    class Meta:
        model = Account
        fields = [
            "display_type",
            "special",
            "unlimited_balance",
            "company",
        ]


class AuthorizedEmailSerializer(serializers.ModelSerializer):
    dependent_of_email = serializers.EmailField(
        source="dependent_of.user.email", read_only=True
    )
    company_name = serializers.CharField(
        source="company.name", read_only=True, allow_null=True
    )
    organism_name = serializers.CharField(
        source="organism.name", read_only=True, allow_null=True
    )
    pending_plate_ids = serializers.PrimaryKeyRelatedField(
        source="pending_plates", many=True, read_only=True
    )
    pending_plate_numbers = serializers.SerializerMethodField()

    def get_pending_plate_numbers(self, obj):
        return list(obj.pending_plates.values_list("plate_number", flat=True))

    class Meta:
        model = AuthorizedEmail
        fields = [
            "id",
            "email",
            "dependent_of",
            "dependent_of_email",
            "special",
            "display_type",
            "unlimited_balance",
            "company",
            "company_name",
            "organism",
            "organism_name",
            "status",
            "invited_at",
            "accepted_at",
            "pending_plate_ids",
            "pending_plate_numbers",
        ]
        read_only_fields = ["status", "invited_at", "accepted_at"]
