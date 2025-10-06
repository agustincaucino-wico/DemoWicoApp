from rest_framework import mixins, viewsets
from rest_framework.permissions import DjangoModelPermissions
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Station, StationAttendantAssignment
from .permissions import AuthenticatedReadDjangoModelPermissions
from .serializers import StationSerializer, StationAttendantAssignmentSerializer


class StationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [AuthenticatedReadDjangoModelPermissions]
    serializer_class = StationSerializer

    def get_queryset(self):
        queryset = Station.objects.select_related("province", "city").order_by("name")
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
    permission_classes = [DjangoModelPermissions]
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
