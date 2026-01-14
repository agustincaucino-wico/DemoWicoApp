from rest_framework import serializers


class RedeemPromotionSerializer(serializers.Serializer):
    """Serializer for redeeming a promotion code"""

    code = serializers.CharField(required=True, max_length=50)
