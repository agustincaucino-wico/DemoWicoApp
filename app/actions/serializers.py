from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from accounts.models import Account, Dependents, DependentInvitation
from users.models import CustomUser


class DependentInvitationSerializer(serializers.ModelSerializer):
    holder_account_email = serializers.CharField(
        source="holder_account.user.email", read_only=True
    )
    holder_account_name = serializers.SerializerMethodField()

    class Meta:
        model = DependentInvitation
        fields = [
            "id",
            "holder_account",
            "dependent_email",
            "invitation_date",
            "status",
            "response_date",
            "holder_account_email",
            "holder_account_name",
        ]
        read_only_fields = [
            "invitation_date",
            "response_date",
        ]

    @extend_schema_field(serializers.CharField)
    def get_holder_account_name(self, obj: DependentInvitation) -> str:
        return f"{obj.holder_account.user.first_name} {obj.holder_account.user.last_name}".strip()


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

        # Validar que el usuario a invitar existe
        try:
            dependent_user = CustomUser.objects.get(email=dependent_email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("No existe un usuario con ese email")

        # Validar que el usuario no se invite a sí mismo
        if request and dependent_user == request.user:
            raise serializers.ValidationError(
                "No puedes enviarte una invitación a ti mismo"
            )

        # Validar que no exista una invitación pendiente
        if DependentInvitation.objects.filter(
            holder_account=holder_account,
            dependent_email=dependent_email,
            status="pending",
        ).exists():
            raise serializers.ValidationError(
                "Ya existe una invitación pendiente para este usuario"
            )

        # Validar que no exista una relación activa
        if Dependents.objects.filter(
            holder_account=holder_account,
            dependent_account__user__email=dependent_email,
            end_date__isnull=True,
        ).exists():
            raise serializers.ValidationError(
                "Ya existe una relación activa entre estas cuentas"
            )

        attrs["holder_account"] = holder_account
        return attrs


class InvitationResponseSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["accept", "reject"],
        help_text="Action to take on the invitation: 'accept' or 'reject'",
    )


class CancelInvitationSerializer(serializers.Serializer):
    holder_account_id = serializers.IntegerField(
        help_text="ID of the holder account that sent the invitation"
    )
    dependent_email = serializers.EmailField(
        help_text="Email of the user whose invitation should be cancelled"
    )


class InvitationsListResponseSerializer(serializers.Serializer):
    sent_invitations = DependentInvitationSerializer(
        many=True, help_text="List of invitations sent by the user's holder accounts"
    )
    received_invitations = DependentInvitationSerializer(
        many=True, help_text="List of invitations received by the user's email"
    )


class RemoveDependentSerializer(serializers.Serializer):
    holder_account_id = serializers.IntegerField(
        help_text="ID of the holder account to remove the dependent from"
    )
    dependent_account_id = serializers.IntegerField(
        help_text="ID of the dependent account to be removed"
    )
