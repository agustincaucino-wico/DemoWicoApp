from rest_framework import mixins, viewsets, status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample

from myapp.permissions import StrictDjangoModelPermissions
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
    AccountBalanceUpdateSerializer,
    DependentsSerializer,
    PlatesSerializer,
    PlatesUpdateSerializer,
    AuthorizedPlateSerializer,
    CompanySerializer,
    CompanyAssignmentSerializer,
)
from actions.serializers import DependentInvitationSerializer


class BaseLCViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication]
    permission_classes = [StrictDjangoModelPermissions]


class BaseLCUDViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet con soporte completo para actualización (PATCH/PUT)"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [StrictDjangoModelPermissions]


class AccountViewSet(BaseLCViewSet):
    queryset = Account.objects.filter(is_active=True).order_by("id")
    serializer_class = AccountSerializer

    @extend_schema(
        request=AccountBalanceUpdateSerializer,
        responses={200: AccountBalanceUpdateSerializer},
        description="Actualiza el balance de una cuenta específica.",
        examples=[
            OpenApiExample(
                "Ejemplo de actualización de balance",
                value={"balance": 1000.50},
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["patch"], url_path="update-balance")
    def update_balance(self, request, pk=None):
        """
        Actualiza únicamente el balance de una cuenta.
        """
        account = self.get_object()
        serializer = AccountBalanceUpdateSerializer(
            account, data=request.data, partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "id": account.id,
                    "balance": account.balance,
                    "message": "Balance actualizado correctamente",
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DependentsViewSet(BaseLCViewSet):
    queryset = Dependents.objects.all().order_by("id")
    serializer_class = DependentsSerializer
    permission_classes = [DjangoModelOrObjectOwner]


class PlatesViewSet(BaseLCUDViewSet):
    queryset = Plates.objects.all().order_by("id")
    serializer_class = PlatesSerializer
    permission_classes = [DjangoModelOrObjectOwner]

    def get_serializer_class(self):
        """Usar PlatesUpdateSerializer solo para actualizaciones (PATCH/PUT)"""
        if self.action in ["update", "partial_update"]:
            return PlatesUpdateSerializer
        return PlatesSerializer


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
