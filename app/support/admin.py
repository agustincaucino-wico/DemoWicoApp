from django.contrib import admin
from .models import ErrorReport
from myapp.admin import my_admin_site


@admin.register(ErrorReport, site=my_admin_site)
class ErrorReportAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "category",
        "status",
        "created_at",
        "updated_at",
    ]
    list_filter = ["category", "status", "created_at"]
    search_fields = ["user__email", "description"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = (
        (
            "Información del Reporte",
            {
                "fields": ("user", "category", "description"),
            },
        ),
        (
            "Estado",
            {
                "fields": ("status",),
            },
        ),
        (
            "Fechas",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )
