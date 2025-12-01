from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from appconfig.models import AppConfig


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
            "maintenance_mode": config.maintenance_mode,
        }
        return Response(payload, status=200)
