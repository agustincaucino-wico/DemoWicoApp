from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from accounts.permissions import IsAdminOrReadOnly
from rest_framework.permissions import DjangoModelPermissions

from .models import (
    Account,
    Dependents,
    Plates,
    AuthorizedPlate,
    Company,
    CompanyAssignment,
)
from .serializers import (
    AccountSerializer,
    DependentsSerializer,
    PlatesSerializer,
    AuthorizedPlateSerializer,
    CompanySerializer,
    CompanyAssignmentSerializer,
)


class BaseLCViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [DjangoModelPermissions]


class AccountViewSet(BaseLCViewSet):
    queryset = Account.objects.all().order_by("id")
    serializer_class = AccountSerializer
    permission_classes = [IsAdminUser]


class DependentsViewSet(BaseLCViewSet):
    queryset = Dependents.objects.all().order_by("id")
    serializer_class = DependentsSerializer


class PlatesViewSet(BaseLCViewSet):
    queryset = Plates.objects.all().order_by("id")
    serializer_class = PlatesSerializer


class AuthorizedPlateViewSet(BaseLCViewSet):
    queryset = AuthorizedPlate.objects.all().order_by("id")
    serializer_class = AuthorizedPlateSerializer


class CompanyViewSet(BaseLCViewSet):
    queryset = Company.objects.all().order_by("id")
    serializer_class = CompanySerializer


class CompanyAssignmentViewSet(BaseLCViewSet):
    queryset = CompanyAssignment.objects.all().order_by("id")
    serializer_class = CompanyAssignmentSerializer
