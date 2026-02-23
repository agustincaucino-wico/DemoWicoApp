from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from .models import AppConfig, BonificationTier
from .serializers import (
    AppConfigSerializer,
    FuelPriceSerializer,
    BonificationTierSerializer,
)


class IsAdminOnly(BasePermission):
    """Solo Administradores y superusuarios pueden modificar la configuración."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        return request.user.groups.filter(name__in=["Administrador", "Admin"]).exists()


class IsAdminOrGestor(BasePermission):
    """Administradores, superusuarios y Gestores pueden ver y modificar el precio de combustible."""

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
    Returns maintenance mode status, public config, and bonification tiers
    with min_amount calculated using the current fuel_price.
    """
    config = AppConfig.get_config()
    fuel_price = config.fuel_price

    tiers = BonificationTier.objects.all()
    tiers_data = BonificationTierSerializer(
        tiers, many=True, context={"fuel_price": fuel_price}
    ).data

    return Response(
        {
            "maintenance_mode": config.maintenance_mode,
            "recharge_cbu": config.recharge_cbu,
            "support_phone": config.support_phone,
            "fuel_price": fuel_price,
            "bonification_tiers": tiers_data,
        }
    )


@api_view(["PATCH"])
@permission_classes([IsAdminOnly])
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


@api_view(["GET"])
@permission_classes([IsAdminOrGestor])
def get_fuel_price(request):
    """
    Obtener el precio de referencia del combustible.
    Solo accesible para Gestores y Administradores.
    """
    config = AppConfig.get_config()
    serializer = FuelPriceSerializer(config)
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAdminOrGestor])
def update_fuel_price(request):
    """
    Actualizar el precio de referencia del combustible.
    Solo accesible para Gestores y Administradores.
    """
    config = AppConfig.get_config()
    serializer = FuelPriceSerializer(config, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
