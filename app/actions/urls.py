from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import InvitationViewSet, UserInfoView, RemoveDependentView
from . import fuel_load_views


router = DefaultRouter()
router.register(r"invitations", InvitationViewSet, basename="invitations")

urlpatterns = [
    path("", include(router.urls)),
    path("info/", UserInfoView.as_view(), name="user-info"),
    path("remove-dependent/", RemoveDependentView.as_view(), name="remove-dependent"),
    # Fuel Load - Cliente
    path(
        "fuel-load/initiate-fuel-load/",
        fuel_load_views.initiate_fuel_load,
        name="initiate-fuel-load",
    ),
    path(
        "fuel-load/cancel-fuel-load/<int:operation_id>/",
        fuel_load_views.cancel_fuel_load,
        name="cancel-fuel-load",
    ),
    # Fuel Load - attendant (playero)
    path(
        "fuel-load/attendant/pending-loads/",
        fuel_load_views.pending_fuel_loads,
        name="pending-fuel-loads",
    ),
    path(
        "fuel-load/attendant/start-fuel-load/",
        fuel_load_views.start_fuel_load,
        name="start-fuel-load",
    ),
    path(
        "fuel-load/attendant/confirm-load/",
        fuel_load_views.complete_fuel_load,
        name="complete-fuel-load",
    ),
    # TODO endpoint para el cliente para consultar el estado de la carga
]
