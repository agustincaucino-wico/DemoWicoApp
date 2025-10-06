from django.contrib import admin

from .models import Station, StationAttendantAssignment


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "province", "city", "street", "street_number")
    list_filter = ("province", "city")
    search_fields = ("name", "street", "city__name", "province__name")


@admin.register(StationAttendantAssignment)
class StationAttendantAssignmentAdmin(admin.ModelAdmin):
    list_display = ("attendant", "station", "start_date", "end_date")
    list_filter = ("station", "start_date", "end_date")
    search_fields = ("attendant__email", "attendant__first_name", "attendant__last_name")
