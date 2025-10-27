from rest_framework import serializers
from notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model"""

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "type",
            "is_read",
            "action_url",
            "created_at",
            "read_at",
        ]
        read_only_fields = ["id", "created_at", "read_at"]


class NotificationListSerializer(serializers.ModelSerializer):
    """Serializer for listing notifications with minimal data"""

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "type",
            "is_read",
            "action_url",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class MarkAsReadSerializer(serializers.Serializer):
    """Serializer for marking notification(s) as read"""

    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of notification IDs to mark as read. If not provided, marks all as read.",
    )


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for NotificationPreference model"""

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "push_enabled",
            "email_enabled",
            "fuel_load_notifications",
            "account_notifications",
            "balance_notifications",
            "system_notifications",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
