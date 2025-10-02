from rest_framework import mixins, viewsets
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import DjangoModelPermissions

from .permissions import DjangoModelOrObjectOwner


from .models import (
    Account,
    Dependents,
    Plates,
    AuthorizedPlate,
    Company,
    CompanyAssignment,
    DependentInvitation,
)
from .serializers import (
    AccountSerializer,
    DependentsSerializer,
    PlatesSerializer,
    AuthorizedPlateSerializer,
    CompanySerializer,
    CompanyAssignmentSerializer,
)
from actions.serializers import DependentInvitationSerializer


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


class DependentsViewSet(BaseLCViewSet):
    queryset = Dependents.objects.all().order_by("id")
    serializer_class = DependentsSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class PlatesViewSet(BaseLCViewSet):
    queryset = Plates.objects.all().order_by("id")
    serializer_class = PlatesSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class AuthorizedPlateViewSet(BaseLCViewSet):
    queryset = AuthorizedPlate.objects.all().order_by("id")
    serializer_class = AuthorizedPlateSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class CompanyViewSet(BaseLCViewSet):
    queryset = Company.objects.all().order_by("id")
    serializer_class = CompanySerializer


class CompanyAssignmentViewSet(BaseLCViewSet):
    queryset = CompanyAssignment.objects.all().order_by("id")
    serializer_class = CompanyAssignmentSerializer


class DependentInvitationsViewSet(BaseLCViewSet):
    queryset = DependentInvitation.objects.all().order_by("-invitation_date")
    serializer_class = DependentInvitationSerializer
    permission_classes = [DjangoModelOrObjectOwner]
