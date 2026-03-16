from decimal import Decimal
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from operation.models import FuelLoadOperation, ModifyFunds, BalanceRechargeRequest


class FuelLoadOperationSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    attendant_name = serializers.SerializerMethodField()
    attendant_email = serializers.SerializerMethodField()
    plate_number = serializers.SerializerMethodField()

    class Meta:
        model = FuelLoadOperation
        fields = "__all__"
        read_only_fields = ("timestamp_started",)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_user_name(self, obj):
        if obj.account and obj.account.user:
            user = obj.account.user
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            return full_name or user.email
        return None

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_user_email(self, obj):
        if obj.account and obj.account.user:
            return obj.account.user.email
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_attendant_name(self, obj):
        if obj.attendant:
            full_name = f"{obj.attendant.first_name or ''} {obj.attendant.last_name or ''}".strip()
            return full_name or obj.attendant.email
        return None

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_attendant_email(self, obj):
        if obj.attendant:
            return obj.attendant.email
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_plate_number(self, obj):
        if obj.plate:
            return obj.plate.plate_number
        return None


class ModifyFundsSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_user_email = serializers.EmailField(
        source="account.user.email", read_only=True
    )
    account_user_full_name = serializers.SerializerMethodField()
    gestor_id = serializers.IntegerField(source="gestor.id", read_only=True)
    gestor_email = serializers.EmailField(source="gestor.email", read_only=True)
    gestor_full_name = serializers.SerializerMethodField()
    payment_method_name = serializers.CharField(
        source="payment_method.name", read_only=True, allow_null=True
    )

    class Meta:
        model = ModifyFunds
        fields = (
            "id",
            "timestamp",
            "amount",
            "comments",
            "payment_method",
            "payment_method_name",
            "account_id",
            "account_user_email",
            "account_user_full_name",
            "gestor_id",
            "gestor_email",
            "gestor_full_name",
        )

    @extend_schema_field(serializers.CharField())
    def get_account_user_full_name(self, obj):
        user = obj.account.user
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        return full_name or user.email

    @extend_schema_field(serializers.CharField())
    def get_gestor_full_name(self, obj):
        gestor = obj.gestor
        full_name = f"{gestor.first_name or ''} {gestor.last_name or ''}".strip()
        return full_name or gestor.email


class BalanceRechargeRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating recharge requests (users)"""

    class Meta:
        model = BalanceRechargeRequest
        fields = (
            "account",
            "amount",
            "transfer_proof",
            "comments",
        )

    def validate_amount(self, value):
        """Validate that amount is positive and within limits"""
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a cero")
        # Límite: 13 dígitos enteros + 2 decimales = 9,999,999,999,999.99
        max_value = Decimal("9999999999999.99")
        if value > max_value:
            raise serializers.ValidationError(
                f"El monto no puede exceder {max_value:,.2f}"
            )
        return value

    def validate_account(self, value):
        """Validate that user owns the account"""
        request = self.context.get("request")
        if request and request.user:
            if value.user != request.user:
                raise serializers.ValidationError(
                    "Solo puedes recargar tus propias cuentas"
                )
        return value

    def create(self, validated_data):
        """Set requested_by to current user"""
        request = self.context.get("request")
        validated_data["requested_by"] = request.user
        return super().create(validated_data)


class BalanceRechargeRequestListSerializer(serializers.ModelSerializer):
    """Serializer for listing recharge requests (with nested data)"""

    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_user_email = serializers.EmailField(
        source="account.user.email", read_only=True
    )
    account_user_full_name = serializers.SerializerMethodField()
    requested_by_email = serializers.EmailField(
        source="requested_by.email", read_only=True
    )
    requested_by_full_name = serializers.SerializerMethodField()
    reviewed_by_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, allow_null=True
    )
    reviewed_by_full_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    transfer_proof_url = serializers.SerializerMethodField()

    class Meta:
        model = BalanceRechargeRequest
        fields = (
            "id",
            "account_id",
            "account_user_email",
            "account_user_full_name",
            "requested_by_email",
            "requested_by_full_name",
            "amount",
            "transfer_proof",
            "transfer_proof_url",
            "comments",
            "status",
            "status_display",
            "reviewed_by_email",
            "reviewed_by_full_name",
            "reviewed_at",
            "review_comments",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_account_user_full_name(self, obj):
        user = obj.account.user
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        return full_name or user.email

    @extend_schema_field(serializers.CharField())
    def get_requested_by_full_name(self, obj):
        user = obj.requested_by
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        return full_name or user.email

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_reviewed_by_full_name(self, obj):
        if not obj.reviewed_by:
            return None
        user = obj.reviewed_by
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        return full_name or user.email

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_transfer_proof_url(self, obj):
        request = self.context.get("request")
        if obj.transfer_proof and request:
            return request.build_absolute_uri(obj.transfer_proof.url)
        return None


class BalanceRechargeRequestDetailSerializer(BalanceRechargeRequestListSerializer):
    """Serializer for detailed view of recharge request"""

    pass


class BalanceRechargeRequestApprovalSerializer(serializers.Serializer):
    """Serializer for approving/rejecting recharge requests"""

    review_comments = serializers.CharField(
        required=False, allow_blank=True, help_text="Comentarios del revisor (opcional)"
    )
