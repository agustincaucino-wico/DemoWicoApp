from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from notifications.models import Notification, NotificationPreference
from notifications.serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    MarkAsReadSerializer,
    NotificationPreferenceSerializer,
)


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user notifications.

    list: Get all notifications for the authenticated user
    retrieve: Get a specific notification
    update/partial_update: Mark a notification as read/unread
    destroy: Delete a notification
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        """Filter notifications to only show the authenticated user's notifications"""
        user = self.request.user
        queryset = Notification.objects.filter(user=user)

        # Filter by read status if provided
        is_read = self.request.query_params.get("is_read", None)
        if is_read is not None:
            if is_read.lower() == "true":
                queryset = queryset.filter(is_read=True)
            elif is_read.lower() == "false":
                queryset = queryset.filter(is_read=False)

        # Filter by type if provided
        notification_type = self.request.query_params.get("type", None)
        if notification_type:
            queryset = queryset.filter(type=notification_type)

        return queryset

    def get_serializer_class(self):
        """Use different serializers for list and detail views"""
        if self.action == "list":
            return NotificationListSerializer
        return NotificationSerializer

    def list(self, request, *args, **kwargs):
        """List notifications with pagination and unread count"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            # Add unread count to response
            response.data["unread_count"] = Notification.get_unread_count(request.user)
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "results": serializer.data,
                "count": queryset.count(),
                "unread_count": Notification.get_unread_count(request.user),
            }
        )

    def retrieve(self, request, *args, **kwargs):
        """Get a specific notification and mark it as read automatically"""
        instance = self.get_object()

        # Automatically mark as read when retrieved
        if not instance.is_read:
            instance.mark_as_read()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        """Update notification (mainly for marking as read/unread)"""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Update read_at timestamp if marking as read
        if "is_read" in request.data and request.data["is_read"]:
            if not instance.is_read:
                serializer.validated_data["read_at"] = timezone.now()

        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all unread notifications as read for the current user"""
        updated_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())

        return Response(
            {
                "message": f"{updated_count} notificaciones marcadas como leídas",
                "updated_count": updated_count,
            }
        )

    @action(detail=False, methods=["post"])
    def mark_as_read(self, request):
        """Mark specific notifications as read"""
        serializer = MarkAsReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification_ids = serializer.validated_data.get("notification_ids", [])

        if notification_ids:
            # Mark specific notifications as read
            updated_count = Notification.objects.filter(
                user=request.user, id__in=notification_ids, is_read=False
            ).update(is_read=True, read_at=timezone.now())
        else:
            # Mark all as read if no IDs provided
            updated_count = Notification.objects.filter(
                user=request.user, is_read=False
            ).update(is_read=True, read_at=timezone.now())

        return Response(
            {
                "message": f"{updated_count} notificaciones marcadas como leídas",
                "updated_count": updated_count,
            }
        )

    @action(detail=False, methods=["delete"])
    def delete_all_read(self, request):
        """Delete all read notifications for the current user"""
        deleted_count, _ = Notification.objects.filter(
            user=request.user, is_read=True
        ).delete()

        return Response(
            {
                "message": f"{deleted_count} notificaciones eliminadas",
                "deleted_count": deleted_count,
            }
        )

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get the count of unread notifications"""
        count = Notification.get_unread_count(request.user)
        return Response({"unread_count": count})


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user notification preferences.

    list/retrieve: Get notification preferences
    update/partial_update: Update notification preferences
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationPreferenceSerializer
    http_method_names = ["get", "put", "patch"]  # Only allow GET, PUT, PATCH

    def get_queryset(self):
        """Filter to only show the authenticated user's preferences"""
        return NotificationPreference.objects.filter(user=self.request.user)

    def get_object(self):
        """Get or create preferences for the current user"""
        obj, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return obj

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Get current user's notification preferences"""
        obj = self.get_object()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @action(detail=False, methods=["put", "patch"])
    def update_preferences(self, request):
        """Update current user's notification preferences"""
        obj = self.get_object()
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
