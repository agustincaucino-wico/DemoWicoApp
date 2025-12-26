from django.urls import include, path
from rest_framework.routers import DefaultRouter

from operation.views import FuelLoadOperationViewSet, ModifyFundsViewSet

router = DefaultRouter()
router.register(
    r"fuel-load-operations",
    FuelLoadOperationViewSet,
    basename="fuel-load-operations",
)
router.register(
    r"modify-funds",
    ModifyFundsViewSet,
    basename="modify-funds",
)

urlpatterns = [
    path("", include(router.urls)),
]
