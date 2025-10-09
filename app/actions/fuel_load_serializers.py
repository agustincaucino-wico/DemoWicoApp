from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field


class InitiateFuelLoadSerializer(serializers.Serializer):
    account = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    station = serializers.IntegerField()
    plate = serializers.IntegerField()


class StartFuelLoadSerializer(serializers.Serializer):
    id_operation = serializers.IntegerField()


class CompleteFuelLoadSerializer(serializers.Serializer):
    id_operation = serializers.IntegerField()
    final_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class CancelFuelLoadResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class PendingFuelLoadSerializer(serializers.Serializer):
    id_operation = serializers.IntegerField(source="id")
    client_full_name = serializers.SerializerMethodField()
    plate = serializers.CharField(source="plate.plate_number")

    @extend_schema_field(serializers.CharField)
    def get_client_full_name(self, obj) -> str:
        user = obj.account.user
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.email
