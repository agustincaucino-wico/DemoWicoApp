from rest_framework import serializers
from .models import PromotionalImage


class RedeemPromotionSerializer(serializers.Serializer):
    """Serializer for redeeming a promotion code"""

    code = serializers.CharField(required=True, max_length=50)


class PromotionalImageSerializer(serializers.ModelSerializer):
    """Serializer for promotional images"""

    image_url = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = PromotionalImage
        fields = [
            "id",
            "title",
            "image",
            "image_url",
            "is_active",
            "order",
            "created_at",
            "updated_at",
            "created_by",
            "created_by_email",
        ]
        read_only_fields = ["created_at", "updated_at", "created_by"]

    def get_image_url(self, obj):
        """Return the full URL for the image"""
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request is not None:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def create(self, validated_data):
        """Automatically set created_by from request user"""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class PromotionalImageListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing active promotional images (public endpoint)"""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PromotionalImage
        fields = ["id", "title", "image_url", "order"]

    def get_image_url(self, obj):
        """Return the full URL for the image"""
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request is not None:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
