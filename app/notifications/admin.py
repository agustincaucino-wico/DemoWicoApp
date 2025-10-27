from django.contrib import admin
from notifications.models import Notification, NotificationPreference
from myapp.admin import my_admin_site


@admin.register(Notification, site=my_admin_site)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model"""

    list_display = ["id", "user", "title", "type", "is_read", "created_at"]
    list_filter = ["type", "is_read", "created_at"]
    search_fields = ["user__email", "title", "message"]
    readonly_fields = ["created_at", "read_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = (
        ("Información básica", {"fields": ("user", "title", "message", "type")}),
        ("Estado", {"fields": ("is_read", "read_at")}),
        ("Acción", {"fields": ("action_url",)}),
        ("Fechas", {"fields": ("created_at",)}),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related("user")

    actions = ["mark_as_read", "mark_as_unread"]

    @admin.action(description="Marcar como leídas")
    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read"""
        from django.utils import timezone

        updated = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(request, f"{updated} notificaciones marcadas como leídas.")

    @admin.action(description="Marcar como no leídas")
    def mark_as_unread(self, request, queryset):
        """Mark selected notifications as unread"""
        updated = queryset.update(is_read=False, read_at=None)
        self.message_user(request, f"{updated} notificaciones marcadas como no leídas.")


@admin.register(NotificationPreference, site=my_admin_site)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for NotificationPreference model"""

    list_display = [
        "id",
        "user",
        "push_enabled",
        "email_enabled",
        "fuel_load_notifications",
        "account_notifications",
        "balance_notifications",
        "system_notifications",
        "updated_at",
    ]
    list_filter = [
        "push_enabled",
        "email_enabled",
        "fuel_load_notifications",
        "account_notifications",
        "balance_notifications",
        "system_notifications",
    ]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"

    fieldsets = (
        ("Usuario", {"fields": ("user",)}),
        ("Canales de notificación", {"fields": ("push_enabled", "email_enabled")}),
        (
            "Tipos de notificaciones",
            {
                "fields": (
                    "fuel_load_notifications",
                    "account_notifications",
                    "balance_notifications",
                    "system_notifications",
                )
            },
        ),
        ("Fechas", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related("user")
