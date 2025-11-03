from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field


class InitiateFuelLoadSerializer(serializers.Serializer):
    account = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    station = serializers.IntegerField()
    plate = serializers.IntegerField(required=False, allow_null=True)
    fill_full_tank = serializers.BooleanField(default=False)


class StartFuelLoadSerializer(serializers.Serializer):
    id_operation = serializers.IntegerField()


class CompleteFuelLoadSerializer(serializers.Serializer):
    id_operation = serializers.IntegerField()
    final_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class CancelFuelLoadRequestSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CancelFuelLoadResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class PendingFuelLoadSerializer(serializers.Serializer):
    id_operation = serializers.IntegerField(source="id")
    client_full_name = serializers.SerializerMethodField()
    plate = serializers.SerializerMethodField()
    status = serializers.CharField()
    initial_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    fill_full_tank = serializers.BooleanField()

    @extend_schema_field(serializers.CharField)
    def get_client_full_name(self, obj) -> str:
        user = obj.account.user
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.email

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_plate(self, obj) -> str | None:
        if obj.plate:
            return obj.plate.plate_number
        return None


class CheckOperationStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    operation_id = serializers.IntegerField()
    final_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )
