from django.contrib import admin
from .models import AppConfig
from myapp.admin import my_admin_site


class AppConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "maintenance_mode", "updated_at")
    readonly_fields = ("updated_at",)

    fieldsets = (
        (
            "Modo Mantenimiento",
            {
                "fields": ("maintenance_mode"),
                "description": "Controla el modo mantenimiento de la aplicación móvil.",
            },
        ),
        (
            "Info",
            {
                "fields": ("updated_at",),
            },
        ),
    )

    def has_add_permission(self, request):
        # Only allow one instance
        return not AppConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False


my_admin_site.register(AppConfig)
