from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ErrorReportViewSet, FleetContactRequestViewSet

router = DefaultRouter()
router.register(r"error-reports", ErrorReportViewSet, basename="error-report")
router.register(
    r"fleet-contact-requests",
    FleetContactRequestViewSet,
    basename="fleet-contact-request",
)

urlpatterns = [
    path("", include(router.urls)),
]
