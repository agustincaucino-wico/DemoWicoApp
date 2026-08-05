from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import FuelType, FuelTypePrice, Station, StationAttendantAssignment


class FuelTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelType
        fields = "__all__"


class FuelTypePriceSerializer(serializers.ModelSerializer):
    fuel_type_name = serializers.CharField(source="fuel_type.name", read_only=True)
    station_name = serializers.CharField(source="station.name", read_only=True)

    class Meta:
        model = FuelTypePrice
        fields = (
            "id",
            "fuel_type",
            "fuel_type_name",
            "station",
            "station_name",
            "price",
            "effective_date",
            "created_at",
        )
        read_only_fields = ("id", "fuel_type_name", "station_name", "created_at")
        validators = [
            UniqueTogetherValidator(
                queryset=FuelTypePrice.objects.all(),
                fields=["station", "fuel_type", "effective_date"],
                message="Ya existe un precio para esa estación, combustible y fecha.",
            )
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a cero.")
        return value


class StationCurrentFuelPriceSerializer(FuelTypePriceSerializer):
    """Serializer de solo lectura para el endpoint de precios vigentes por estación."""

    class Meta(FuelTypePriceSerializer.Meta):
        read_only_fields = FuelTypePriceSerializer.Meta.fields


class StationSerializer(serializers.ModelSerializer):
    province_name = serializers.CharField(source="province.name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)
    lat = serializers.FloatField(required=False, allow_null=True)
    lon = serializers.FloatField(required=False, allow_null=True)
    expendio = serializers.ChoiceField(
        choices=[("", ""), *Station.EXPENDIO_CHOICES],
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    class Meta:
        model = Station
        fields = (
            "id",
            "name",
            "province",
            "province_name",
            "city",
            "city_name",
            "street",
            "street_number",
            "lat",
            "lon",
            "is_active",
            "expendio",
        )
        read_only_fields = ("id", "province_name", "city_name")


class StationAttendantAssignmentSerializer(serializers.ModelSerializer):
    attendant_email = serializers.EmailField(source="attendant.email", read_only=True)
    attendant_full_name = serializers.SerializerMethodField()
    station_name = serializers.CharField(source="station.name", read_only=True)

    class Meta:
        model = StationAttendantAssignment
        fields = (
            "id",
            "attendant",
            "attendant_email",
            "attendant_full_name",
            "station",
            "station_name",
            "start_date",
            "end_date",
        )
        read_only_fields = (
            "id",
            "attendant_email",
            "attendant_full_name",
            "station_name",
        )

    def get_attendant_full_name(self, obj: StationAttendantAssignment) -> str:
        return obj.attendant.get_full_name() or obj.attendant.email
