from rest_framework import serializers
from .models import AppConfig


class AppConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppConfig
        fields = ["maintenance_mode", "recharge_cbu", "support_phone", "updated_at"]
        read_only_fields = ["updated_at"]
