from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(
    summary="Health check endpoint",
    description="Returns service health status, API version and minimum required app version",
    responses={200: OpenApiTypes.OBJECT},
)
class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        payload = {
            "status": "ok",
            "api_version": getattr(settings, "API_VERSION", None),
            "min_app_version": getattr(settings, "MIN_APP_VERSION", None),
        }
        return Response(payload, status=200)
