from django.urls import path
from . import views

urlpatterns = [
    path("config/", views.get_app_config, name="app-config"),
    path("config/update/", views.update_app_config, name="app-config-update"),
    path("config/fuel-price/", views.get_fuel_price, name="fuel-price"),
    path(
        "config/fuel-price/update/", views.update_fuel_price, name="fuel-price-update"
    ),
]
