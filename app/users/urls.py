from users import views
from users.password_reset_views import (
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
)
from django.urls import include, path
from rest_framework import routers


router = routers.DefaultRouter()
router.register(r"", views.UserViewSet, basename="users")

urlpatterns = [
    path(
        "password-reset-request/",
        PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "password-reset-verify/",
        PasswordResetVerifyView.as_view(),
        name="password-reset-verify",
    ),
    path(
        "password-reset-confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("", include(router.urls)),
]
