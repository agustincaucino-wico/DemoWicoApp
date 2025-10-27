from django.urls import path, include
from rest_framework import routers
from notifications import views

router = routers.DefaultRouter()
router.register(r"", views.NotificationViewSet, basename="notifications")
router.register(
    r"preferences",
    views.NotificationPreferenceViewSet,
    basename="notification-preferences",
)

urlpatterns = [
    path("", include(router.urls)),
]
