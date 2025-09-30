from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from .models import Setting
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from typing import List

# from django.contrib.auth.models import User

UserModel = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    groups = serializers.SerializerMethodField()

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
            "gender",
            "groups",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_groups(self, obj) -> List[str]:
        return [group.name for group in obj.groups.all()]

    def create(self, validated_data):
        user = UserModel.objects.create_user(**validated_data)
        group, created = Group.objects.get_or_create(name="Cliente")
        user.groups.add(group)
        return user


class SettingSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Setting
        fields = "__all__"
