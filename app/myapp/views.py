from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema


@extend_schema(
    summary="Health check",
    description="Simple health endpoint to verify the API is running.",
    responses={200: {"type": "object"}},
)
class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"}, status=200)
