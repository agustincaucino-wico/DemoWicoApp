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

urlpatterns = [
    path("", include(router.urls)),
]
