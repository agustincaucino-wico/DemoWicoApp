from django.urls import path
from . import views

urlpatterns = [
    path("config/", views.get_app_config, name="app-config"),
    path("config/update/", views.update_app_config, name="app-config-update"),
]

