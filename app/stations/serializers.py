from rest_framework import serializers

from .models import FuelType, FuelTypePrice, Station, StationAttendantAssignment


class FuelTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelType
        fields = "__all__"


class FuelTypePriceSerializer(serializers.ModelSerializer):
    fuel_type_name = serializers.CharField(source="fuel_type.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = FuelTypePrice
        fields = "__all__"


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
