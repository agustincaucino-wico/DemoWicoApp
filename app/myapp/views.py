from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from appconfig.models import AppConfig
from .store_version import get_latest_ios_version, get_latest_android_version


def get_docs_permission():
    """Return AllowAny in DEBUG mode, IsAdminUser in production."""
    return [AllowAny] if settings.DEBUG else [IsAdminUser]


class AdminSpectacularAPIView(SpectacularAPIView):
    """API Schema view - open in dev, admin-only in production."""

    def get_permissions(self):
        return [perm() for perm in get_docs_permission()]


class AdminSpectacularSwaggerView(SpectacularSwaggerView):
    """Swagger UI view - open in dev, admin-only in production."""

    def get_permissions(self):
        return [perm() for perm in get_docs_permission()]


@extend_schema(
    summary="Health check endpoint",
    description="Returns service health status, API version, minimum required app version, and maintenance mode",
    responses={200: OpenApiTypes.OBJECT},
)
class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        config = AppConfig.get_config()

        payload = {
            "status": "ok",
            "api_version": getattr(settings, "API_VERSION", None),
            "min_app_version": getattr(settings, "MIN_APP_VERSION", None),
            "latest_ios_version": get_latest_ios_version(),
            "latest_android_version": get_latest_android_version(),
            "maintenance_mode": config.maintenance_mode,
        }
        return Response(payload, status=200)
