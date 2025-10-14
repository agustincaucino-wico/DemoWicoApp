from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ErrorReportViewSet

router = DefaultRouter()
router.register(r"error-reports", ErrorReportViewSet, basename="error-report")

urlpatterns = [
    path("", include(router.urls)),
]
