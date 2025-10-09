from rest_framework import serializers

from operation.models import FuelLoadOperation


class FuelLoadOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelLoadOperation
        fields = "__all__"
        read_only_fields = ("timestamp_started",)
