from django.contrib import admin
from .models import Country, Province, City, Address
from myapp.admin import my_admin_site


class CountryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "country")
    search_fields = ("name", "country__name")
    list_filter = ("country",)


class CityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "province")
    search_fields = ("name", "province__name")
    list_filter = ("province",)


class AddressAdmin(admin.ModelAdmin):
    list_display = ("id", "street", "number", "floor", "apartment", "city")
    search_fields = ("street", "city__name")
    list_filter = ("city",)


my_admin_site.register(Country, CountryAdmin)
my_admin_site.register(Province, ProvinceAdmin)
my_admin_site.register(City, CityAdmin)
my_admin_site.register(Address, AddressAdmin)
