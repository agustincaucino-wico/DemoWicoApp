from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Account, Dependents, Plates, AuthorizedPlate, DependentInvitation
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


class RemoveDependentSerializer(serializers.Serializer):
    holder_account_id = serializers.IntegerField(
        help_text="ID of the holder account to remove the dependent from"
    )
    dependent_account_id = serializers.IntegerField(
        help_text="ID of the dependent account to be removed"
    )


class DependentInvitationSerializer(serializers.ModelSerializer):
    holder_account_email = serializers.CharField(
        source="holder_account.user.email", read_only=True
    )
    dependent_account_email = serializers.CharField(
        source="dependent_account.user.email", read_only=True
    )
    holder_account_name = serializers.SerializerMethodField()
    dependent_account_name = serializers.SerializerMethodField()

    class Meta:
        model = DependentInvitation
        fields = [
            "id",
            "holder_account",
            "dependent_account",
            "invitation_date",
            "status",
            "response_date",
            "holder_account_email",
            "dependent_account_email",
            "holder_account_name",
            "dependent_account_name",
        ]
        read_only_fields = [
            "invitation_date",
            "response_date",
        ]

    @extend_schema_field(serializers.CharField)
    def get_holder_account_name(self, obj: DependentInvitation) -> str:
        return f"{obj.holder_account.user.first_name} {obj.holder_account.user.last_name}".strip()

    @extend_schema_field(serializers.CharField)
    def get_dependent_account_name(self, obj: DependentInvitation) -> str:
        return f"{obj.dependent_account.user.first_name} {obj.dependent_account.user.last_name}".strip()


class CreateInvitationSerializer(serializers.Serializer):
    holder_account_id = serializers.IntegerField(
        help_text="ID of the holder account sending the invitation"
    )
    dependent_email = serializers.EmailField(
        help_text="Email of the user to be invited as a dependent"
    )

    def validate(self, attrs):
        holder_account_id = attrs.get("holder_account_id")
        dependent_email = attrs.get("dependent_email")

        # Validar que la cuenta titular existe y pertenece al usuario
        request = self.context.get("request")
        if request:
            try:
                holder_account = Account.objects.get(
                    id=holder_account_id, user=request.user, account_type="holder"
                )
            except Account.DoesNotExist:
                raise serializers.ValidationError(
                    "La cuenta titular no existe o no te pertenece"
                )

        # Validar que el usuario a invitar existe y tiene cuenta dependiente
        try:
            from users.models import CustomUser

            dependent_user = CustomUser.objects.get(email=dependent_email)
            dependent_account = Account.objects.get(
                user=dependent_user, account_type="dependent"
            )
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("No existe un usuario con ese email")
        except Account.DoesNotExist:
            raise serializers.ValidationError(
                "El usuario no tiene una cuenta dependiente"
            )

        # Validar que no exista una invitación pendiente
        if DependentInvitation.objects.filter(
            holder_account=holder_account,
            dependent_account=dependent_account,
            status="pending",
        ).exists():
            raise serializers.ValidationError(
                "Ya existe una invitación pendiente para este usuario"
            )

        # Validar que no exista una relación activa
        if Dependents.objects.filter(
            holder_account=holder_account,
            dependent_account=dependent_account,
            end_date__isnull=True,
        ).exists():
            raise serializers.ValidationError(
                "Ya existe una relación activa entre estas cuentas"
            )

        attrs["holder_account"] = holder_account
        attrs["dependent_account"] = dependent_account
        return attrs


class InvitationResponseSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["accept", "reject"],
        help_text="Action to take on the invitation: 'accept' or 'reject'",
    )
