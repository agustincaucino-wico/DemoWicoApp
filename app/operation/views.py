from rest_framework import mixins, viewsets
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication

from operation.models import FuelLoadOperation, ModifyFunds
from operation.serializers import FuelLoadOperationSerializer, ModifyFundsSerializer
from myapp.permissions import StrictDjangoModelPermissions


class BaseLCDViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [StrictDjangoModelPermissions]


class IsAdminRole(BasePermission):
    admin_groups = {"Gestor", "Administrador", "Admin"}

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        return user.groups.filter(name__in=self.admin_groups).exists()


class FuelLoadOperationViewSet(BaseLCDViewSet):
    """
    API endpoint allowing creation, listing and deletion of fuel load operations.
    """

    serializer_class = FuelLoadOperationSerializer

    def get_queryset(self):
        queryset = (
            FuelLoadOperation.objects.select_related(
                "account__user",
                "plate",
                "attendant",
                "station",
                "payment_method",
            )
            .all()
            .order_by("-timestamp_started")
        )

        station_id = self.request.query_params.get("station")
        status = self.request.query_params.get("status")
        attendant_id = self.request.query_params.get("attendant")

        if station_id:
            queryset = queryset.filter(station_id=station_id)
        if status:
            queryset = queryset.filter(status=status)
        if attendant_id:
            queryset = queryset.filter(attendant_id=attendant_id)

        return queryset


class ModifyFundsViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminRole]
    serializer_class = ModifyFundsSerializer

    def get_queryset(self):
        return (
            ModifyFunds.objects.select_related("account__user", "gestor", "payment_method")
            .all()
            .order_by("-timestamp")
        )
