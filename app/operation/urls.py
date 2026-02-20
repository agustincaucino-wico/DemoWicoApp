from django.urls import include, path
from rest_framework.routers import DefaultRouter

from operation.views import (
    FuelLoadOperationViewSet,
    ModifyFundsViewSet,
    BalanceRechargeRequestViewSet,
)

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
router.register(
    r"recharge-requests",
    BalanceRechargeRequestViewSet,
    basename="recharge-requests",
)

urlpatterns = [
    path("", include(router.urls)),
]
