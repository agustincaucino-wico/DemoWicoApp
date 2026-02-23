from rest_framework import serializers
from .models import AppConfig, BonificationTier


class BonificationTierSerializer(serializers.ModelSerializer):
    min_amount = serializers.SerializerMethodField()

    class Meta:
        model = BonificationTier
        fields = [
            "id",
            "min_liters",
            "bonus_percent",
            "color_intensity",
            "order",
            "min_amount",
        ]

    def get_min_amount(self, obj):
        fuel_price = self.context.get("fuel_price")
        if fuel_price is not None:
            return float(obj.min_liters) * float(fuel_price)
        return None


class AppConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppConfig
        fields = ["maintenance_mode", "recharge_cbu", "support_phone", "updated_at"]
        read_only_fields = ["updated_at"]


class FuelPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppConfig
        fields = ["fuel_price", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_fuel_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "El precio de combustible no puede ser negativo."
            )
        return value
