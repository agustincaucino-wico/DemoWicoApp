from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from typing import List
from locations.models import Province, City

# from django.contrib.auth.models import User

UserModel = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    dni = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    gender = serializers.ChoiceField(
        choices=["M", "F"], required=False, allow_null=True
    )
    phone_number = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    id_province = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(), required=False, allow_null=True
    )
    id_city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), required=False, allow_null=True
    )
    groups = serializers.SerializerMethodField()
    province_name = serializers.SerializerMethodField()
    city_name = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = UserModel
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "dni",
            "phone_number",
            "id_province",
            "province_name",
            "id_city",
            "city_name",
            "gender",
            "groups",
            "date_joined",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_groups(self, obj) -> List[str]:
        return [group.name for group in obj.groups.all()]

    def create(self, validated_data):
        user = UserModel.objects.create_user(**validated_data)
        group, created = Group.objects.get_or_create(name="Cliente")
        user.groups.add(group)
        return user

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_province_name(self, obj) -> str | None:
        province = getattr(obj, "id_province", None)
        return province.name if province else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_city_name(self, obj) -> str | None:
        city = getattr(obj, "id_city", None)
        return city.name if city else None
