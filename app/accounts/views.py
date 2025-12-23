from rest_framework import mixins, viewsets, status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample
from django.utils import timezone

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
        description="Actualiza el balance de una cuenta específica. Crea un registro en ModifyFunds.",
        examples=[
            OpenApiExample(
                "Ejemplo de actualización de balance",
                value={
                    "balance": 1000.50,
                    "comments": "Pago de cliente X",
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["patch"], url_path="update-balance")
    def update_balance(self, request, pk=None):
        """
        Actualiza únicamente el balance de una cuenta.
        También crea un registro en ModifyFunds con comentarios.
        """
        from operation.models import ModifyFunds, PaymentMethod
        from django.db import transaction

        account = self.get_object()
        serializer = AccountBalanceUpdateSerializer(
            account, data=request.data, partial=True
        )

        if serializer.is_valid():
            new_balance = serializer.validated_data.get("balance")
            amount_change = new_balance - account.balance
            comments = serializer.validated_data.get("comments", "")

            try:
                with transaction.atomic():
                    # Actualizar el balance
                    serializer.save()

                    # Crear entrada en ModifyFunds
                    ModifyFunds.objects.create(
                        account=account,
                        gestor=request.user,
                        amount=amount_change,
                        payment_method=None,  # Metodo de pago no implementado aun TODO
                        comments=comments or None,
                    )

                return Response(
                    {
                        "id": account.id,
                        "balance": account.balance,
                        "message": "Balance actualizado correctamente",
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"error": f"Error al actualizar el balance: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
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

    def get_queryset(self):
        """
        Filtrar solo patentes activas (end_date null) para listados.
        Para retrieve, update y delete, devolver todas para permitir operaciones.
        """
        if self.action == "list":
            return Plates.objects.filter(end_date__isnull=True).order_by("id")
        return super().get_queryset()

    def get_serializer_class(self):
        """Usar PlatesUpdateSerializer solo para actualizaciones (PATCH/PUT)"""
        if self.action in ["update", "partial_update"]:
            return PlatesUpdateSerializer
        return PlatesSerializer

    def create(self, request, *args, **kwargs):
        """
        Crear una nueva patente, pero primero verificar que no exista
        una patente activa (end_date nulo) con el mismo número.
        """
        plate_number = request.data.get("plate_number", "").upper().strip()

        if plate_number:
            # Verificar si existe una patente activa con este número
            existing_active_plate = Plates.objects.filter(
                plate_number=plate_number, end_date__isnull=True
            ).first()

            if existing_active_plate:
                return Response(
                    {"error": "Esta patente ya esta registrada."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        En lugar de eliminar la patente, se le asigna una end_date (soft delete).
        """
        plate = self.get_object()

        # Verificar si ya tiene end_date
        if plate.end_date is not None:
            return Response(
                {"error": "Esta patente ya fue dada de baja anteriormente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Asignar la fecha de fin (soft delete)
        plate.end_date = timezone.now().date()
        plate.save()

        return Response(
            {
                "message": f"La patente '{plate.plate_number}' fue dada de baja exitosamente.",
                "end_date": plate.end_date,
            },
            status=status.HTTP_200_OK,
        )


class AuthorizedPlateViewSet(BaseLCViewSet):
    queryset = AuthorizedPlate.objects.all().order_by("id")
    serializer_class = AuthorizedPlateSerializer
    permission_classes = [DjangoModelOrObjectOwner]

    def get_queryset(self):
        """
        Filtrar solo autorizaciones activas (end_date null) para listados.
        También verificar que la patente asociada esté activa.
        """
        if self.action == "list":
            return AuthorizedPlate.objects.filter(
                end_date__isnull=True, plate__end_date__isnull=True
            ).order_by("id")
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        """
        Crear una nueva autorización de patente, pero primero verificar que no exista
        una autorización activa (end_date nulo) para la misma patente y cuenta dependiente.
        """
        plate_id = request.data.get("plate")
        dependent_account_id = request.data.get("dependent_account")

        if plate_id and dependent_account_id:
            # Verificar si existe una autorización activa
            existing_active_auth = AuthorizedPlate.objects.filter(
                plate_id=plate_id,
                dependent_account_id=dependent_account_id,
                end_date__isnull=True,
            ).first()

            if existing_active_auth:
                return Response(
                    {
                        "error": "Ya existe una autorización activa para esta patente y cuenta dependiente. "
                        "No se puede crear una nueva autorización."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        En lugar de eliminar la autorización, se le asigna una end_date (soft delete).
        """
        authorized_plate = self.get_object()

        # Verificar si ya tiene end_date
        if authorized_plate.end_date is not None:
            return Response(
                {"error": "Esta autorización ya fue revocada anteriormente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Asignar la fecha de fin (soft delete)
        authorized_plate.end_date = timezone.now().date()
        authorized_plate.save()

        return Response(
            {
                "message": f"La autorización de la patente '{authorized_plate.plate.plate_number}' fue revocada exitosamente.",
                "end_date": authorized_plate.end_date,
            },
            status=status.HTTP_200_OK,
        )


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
