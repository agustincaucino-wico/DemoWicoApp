from django.urls import include, path
from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r"stations", views.StationViewSet, basename="stations")
router.register(
    r"attendant-assignments",
    views.StationAttendantAssignmentViewSet,
    basename="station-attendant-assignments",
)
router.register(r"fuel-types", views.FuelTypeViewSet, basename="fuel-types")
router.register(
    r"fuel-type-prices", views.FuelTypePriceViewSet, basename="fuel-type-prices"
)

urlpatterns = [
    path("", include(router.urls)),
]
