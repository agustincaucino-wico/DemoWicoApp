from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    AccountViewSet,
    DependentsViewSet,
    PlatesViewSet,
    AuthorizedPlateViewSet,
    CompanyViewSet,
    CompanyAssignmentViewSet,
    DependentInvitationsViewSet,
    OrganismViewSet,
    AuthorizedEmailViewSet,
)


router = DefaultRouter()
router.register(r"accounts", AccountViewSet)
router.register(r"dependents", DependentsViewSet)
router.register(r"plates", PlatesViewSet)
router.register(r"authorized-plates", AuthorizedPlateViewSet)
router.register(r"companies", CompanyViewSet)
router.register(r"company-assignments", CompanyAssignmentViewSet)
router.register(
    r"dependent-invitations",
    DependentInvitationsViewSet,
    basename="dependent-invitations",
)
router.register(r"organisms", OrganismViewSet)
router.register(r"authorized-emails", AuthorizedEmailViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
