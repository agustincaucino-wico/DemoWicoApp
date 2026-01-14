from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from operation.models import FuelLoadOperation, ModifyFunds


class FuelLoadOperationSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    attendant_name = serializers.SerializerMethodField()
    attendant_email = serializers.SerializerMethodField()

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
