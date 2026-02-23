from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from .models import AppConfig
from .serializers import AppConfigSerializer


class IsAdminOrGestor(BasePermission):
    """Solo Administradores, Gestores y superusuarios pueden modificar la configuración."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        return request.user.groups.filter(
            name__in=["Administrador", "Admin", "Gestor"]
        ).exists()


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


@api_view(["PATCH"])
@permission_classes([IsAdminOrGestor])
def update_app_config(request):
    """
    Partially update app configuration. Restricted to Admins and Gestores.
    """
    config = AppConfig.get_config()
    serializer = AppConfigSerializer(config, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
