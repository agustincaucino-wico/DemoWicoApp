from django.contrib import admin

from myapp.admin import my_admin_site
from operation.models import FuelLoadOperation, PaymentMethod


@admin.register(PaymentMethod, site=my_admin_site)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(FuelLoadOperation, site=my_admin_site)
class FuelLoadOperationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account",
        "plate",
        "station",
        "attendant",
        "initial_amount",
        "final_amount",
        "status",
        "payment_method",
        "timestamp_started",
    )
    list_filter = ("status", "payment_method", "timestamp_started")
    search_fields = (
        "account__user__email",
        "plate__plate_number",
        "station__name",
        "attendant__email",
    )
    autocomplete_fields = ("account", "plate", "attendant", "station", "payment_method")
