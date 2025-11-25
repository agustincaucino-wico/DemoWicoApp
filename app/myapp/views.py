from django.http import JsonResponse
from django.views import View
from django.conf import settings


class HealthCheckView(View):
    def get(self, request, *args, **kwargs):
        payload = {"status": "ok"}
        # Add application version read from settings (loaded from .env)
        try:
            payload["app_version"] = settings.APP_VERSION
        except Exception:
            # Keep endpoint resilient if settings doesn't expose APP_VERSION
            payload["app_version"] = None
        return JsonResponse(payload, status=200)
