from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import AppConfig


@api_view(["GET"])
@permission_classes([AllowAny])
def get_app_config(request):
    """
    Get app configuration (public endpoint).
    Returns maintenance mode status and other public config.
    """
    config = AppConfig.get_config()

    return Response(
        {
            "maintenance_mode": config.maintenance_mode,
            "recharge_cbu": config.recharge_cbu,
            "support_phone": config.support_phone,
        }
    )
