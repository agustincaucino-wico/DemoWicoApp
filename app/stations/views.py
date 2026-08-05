from datetime import datetime

from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import Group
from django.utils import timezone

from myapp.permissions import StrictDjangoModelPermissions
from .models import FuelType, FuelTypePrice, Station, StationAttendantAssignment
from .permissions import AuthenticatedReadDjangoModelPermissions
from .serializers import (
    FuelTypeSerializer,
    FuelTypePriceSerializer,
    StationCurrentFuelPriceSerializer,
    StationSerializer,
    StationAttendantAssignmentSerializer,
)


class FuelTypeViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD de tipos de combustible. Lectura para cualquier usuario autenticado, escritura solo Gestores."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [AuthenticatedReadDjangoModelPermissions]
    queryset = FuelType.objects.all().order_by("name")
    serializer_class = FuelTypeSerializer


class FuelTypePriceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD de precios de combustible por estación. Lectura para cualquier usuario
    autenticado (la app), escritura solo para Gestores."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [AuthenticatedReadDjangoModelPermissions]
    serializer_class = FuelTypePriceSerializer

    def get_queryset(self):
        queryset = FuelTypePrice.objects.select_related("fuel_type", "station")

        fuel_type_id = self.request.query_params.get("fuel_type")
        station_id = self.request.query_params.get("station")
        effective_date_from = self.request.query_params.get("effective_date_from")
        effective_date_to = self.request.query_params.get("effective_date_to")

        if fuel_type_id:
            queryset = queryset.filter(fuel_type_id=fuel_type_id)
        if station_id:
            queryset = queryset.filter(station_id=station_id)
        if effective_date_from:
            parsed = self._parse_date(effective_date_from)
            if parsed:
                queryset = queryset.filter(effective_date__gte=parsed)
        if effective_date_to:
            parsed = self._parse_date(effective_date_to)
            if parsed:
                queryset = queryset.filter(effective_date__lte=parsed)

        return queryset

    @staticmethod
    def _parse_date(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        """
        Devuelve el precio vigente (mayor `effective_date` <= hoy) de cada
        combinación (estación, tipo de combustible), excluyendo estaciones y
        tipos de combustible inactivos. Acepta los filtros opcionales
        `station` y `fuel_type`.
        """
        queryset = (
            FuelTypePrice.objects.filter(
                effective_date__lte=timezone.localdate(),
                fuel_type__is_active=True,
                station__is_active=True,
            )
            .select_related("fuel_type", "station")
        )

        fuel_type_id = request.query_params.get("fuel_type")
        station_id = request.query_params.get("station")
        if fuel_type_id:
            queryset = queryset.filter(fuel_type_id=fuel_type_id)
        if station_id:
            queryset = queryset.filter(station_id=station_id)

        queryset = queryset.order_by(
            "station_id", "fuel_type_id", "-effective_date", "-id"
        ).distinct("station_id", "fuel_type_id")

        serializer = StationCurrentFuelPriceSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class StationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [AuthenticatedReadDjangoModelPermissions]
    serializer_class = StationSerializer

    def get_queryset(self):
        queryset = Station.objects.select_related("province", "city").order_by("name")

        # Solo filtrar por is_active en operaciones de lista (GET)
        # Para UPDATE/DELETE/etc, necesitamos acceso a todas las estaciones
        if self.action == "list":
            include_inactive = (
                self.request.query_params.get("include_inactive", "false").lower()
                == "true"
            )
            if not include_inactive:
                queryset = queryset.filter(is_active=True)
                # Ocultar estaciones de Córdoba a usuarios que no tienen una cuenta con special="cordoba"
                user = self.request.user
                has_cordoba_account = user.account_set.filter(
                    special="cordoba", is_active=True
                ).exists()
                if not has_cordoba_account:
                    queryset = queryset.exclude(expendio__iexact="cordoba")

        province_id = self.request.query_params.get("province")
        city_id = self.request.query_params.get("city")
        if province_id:
            queryset = queryset.filter(province_id=province_id)
        if city_id:
            queryset = queryset.filter(city_id=city_id)
        return queryset


class StationAttendantAssignmentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [StrictDjangoModelPermissions]
    serializer_class = StationAttendantAssignmentSerializer

    def get_queryset(self):
        queryset = (
            StationAttendantAssignment.objects.select_related(
                "attendant",
                "station",
                "station__city",
                "station__province",
            )
            .all()
            .order_by("-start_date", "attendant__id")
        )

        station_id = self.request.query_params.get("station")
        attendant_id = self.request.query_params.get("attendant")
        if station_id:
            queryset = queryset.filter(station_id=station_id)
        if attendant_id:
            queryset = queryset.filter(attendant_id=attendant_id)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """
        Al desasignar una estación, se establece end_date y se remueve el rol de Encargado si el usuario lo tiene.
        """
        from datetime import date

        assignment = self.get_object()
        attendant = assignment.attendant

        # No eliminar, sino establecer end_date
        assignment.end_date = date.today()
        assignment.save()

        # Remover el rol de Encargado si el usuario lo tiene
        try:
            encargado_group = Group.objects.get(name="Encargado")
            if attendant.groups.filter(id=encargado_group.id).exists():
                attendant.groups.remove(encargado_group)
        except Group.DoesNotExist:
            pass

        return Response(
            {
                "message": "Estación desasignada correctamente. El rol de Encargado ha sido removido.",
                "attendant_id": attendant.id,
                "attendant_email": attendant.email,
            },
            status=status.HTTP_200_OK,
        )
