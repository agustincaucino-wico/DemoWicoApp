from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import Country, Province, City, Address


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = "__all__"


class ProvinceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Province
        fields = "__all__"


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = "__all__"

    def validate(self, attrs):
        # Ensure the provided province exists
        province = attrs.get("province")
        if province is None:
            raise ValidationError({"province": "Province is required."})
        if not Province.objects.filter(pk=getattr(province, "pk", province)).exists():
            raise ValidationError({"province": "Province does not exist."})
        return attrs


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = "__all__"

    def validate(self, attrs):
        # Ensure city exists
        city = attrs.get("city")
        if city is None:
            raise ValidationError({"city": "City is required."})
        if not City.objects.filter(pk=getattr(city, "pk", city)).exists():
            raise ValidationError({"city": "City does not exist."})

        # Basic validation for number
        number = attrs.get("number")
        if number is not None and number <= 0:
            raise ValidationError({"number": "Number must be a positive integer."})

        return attrs
