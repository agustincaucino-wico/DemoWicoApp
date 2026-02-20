from rest_framework import mixins, viewsets, status
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import Group

from myapp.permissions import StrictDjangoModelPermissions
from .models import Station, StationAttendantAssignment
from .permissions import AuthenticatedReadDjangoModelPermissions
from .serializers import StationSerializer, StationAttendantAssignmentSerializer


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
