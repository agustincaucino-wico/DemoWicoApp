from django.contrib import admin

from myapp.admin import my_admin_site
from operation.models import FuelLoadOperation, PaymentMethod, Transfer


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
        "fill_full_tank",
        "status",
        "payment_method",
        "timestamp_started",
    )
    list_filter = ("status", "fill_full_tank", "payment_method", "timestamp_started")
    search_fields = (
        "account__user__email",
        "plate__plate_number",
        "station__name",
        "attendant__email",
    )
    autocomplete_fields = ("account", "plate", "attendant", "station", "payment_method")


@admin.register(Transfer, site=my_admin_site)
class TransferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_account",
        "destination_account",
        "amount",
        "timestamp",
    )
    list_filter = ("timestamp",)
    search_fields = (
        "source_account__user__email",
        "destination_account__user__email",
    )
    autocomplete_fields = ("source_account", "destination_account")
    readonly_fields = ("timestamp",)
