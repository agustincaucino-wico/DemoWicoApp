from users import views
from users.password_reset_views import (
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
)
from users.views import DevUserListView, DevUserLoginView
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
    # Dev-only endpoints
    path("dev/list/", DevUserListView.as_view(), name="dev-user-list"),
    path("dev/login/", DevUserLoginView.as_view(), name="dev-user-login"),
    path("", include(router.urls)),
]
