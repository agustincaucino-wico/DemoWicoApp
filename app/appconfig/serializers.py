import math

from rest_framework import serializers
from .models import AppConfig, BonificationTier


def round_down_to_thousand(value):
    """Redondea hacia abajo al millar más cercano."""
    return math.floor(value / 1000) * 1000


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
            raw = float(obj.min_liters) * float(fuel_price)
            return round_down_to_thousand(raw)
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
