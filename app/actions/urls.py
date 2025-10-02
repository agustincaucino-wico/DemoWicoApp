from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import InvitationViewSet, UserInfoView, RemoveDependentView


router = DefaultRouter()
router.register(r"invitations", InvitationViewSet, basename="invitations")

urlpatterns = [
    path("", include(router.urls)),
    path("info/", UserInfoView.as_view(), name="user-info"),
    path("remove-dependent/", RemoveDependentView.as_view(), name="remove-dependent"),
]
