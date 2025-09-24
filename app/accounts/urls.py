from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    AccountViewSet,
    DependentsViewSet,
    PlatesViewSet,
    AuthorizedPlateViewSet,
    CompanyViewSet,
    CompanyAssignmentViewSet,
    UserActionsViewSet,
)


router = DefaultRouter()
router.register(r"accounts", AccountViewSet)
router.register(r"dependents", DependentsViewSet)
router.register(r"plates", PlatesViewSet)
router.register(r"authorized-plates", AuthorizedPlateViewSet)
router.register(r"companies", CompanyViewSet)
router.register(r"company-assignments", CompanyAssignmentViewSet)
router.register(r"user-actions", UserActionsViewSet, basename="user-actions")

urlpatterns = [
    path("", include(router.urls)),
]
