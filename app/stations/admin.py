from django.contrib import admin
from myapp.admin import my_admin_site

from .models import FuelType, FuelTypePrice, Station, StationAttendantAssignment


@admin.register(FuelType, site=my_admin_site)
class FuelTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(FuelTypePrice, site=my_admin_site)
class FuelTypePriceAdmin(admin.ModelAdmin):
    list_display = ("id", "fuel_type", "company", "price", "effective_date")
    search_fields = ("fuel_type__name", "company__name")
    list_filter = ("fuel_type", "effective_date")
    autocomplete_fields = ("fuel_type", "company")


@admin.register(Station, site=my_admin_site)
class StationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "province",
        "city",
        "street",
        "street_number",
        "is_active",
        "lat",
        "lon",
        "expendio",
    )
    list_filter = ("province", "city", "is_active")
    search_fields = ("name", "street", "city__name", "province__name", "expendio")


@admin.register(StationAttendantAssignment, site=my_admin_site)
class StationAttendantAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "attendant", "station", "start_date", "end_date")
    list_filter = ("station", "start_date", "end_date")
    search_fields = (
        "attendant__email",
        "attendant__first_name",
        "attendant__last_name",
    )
