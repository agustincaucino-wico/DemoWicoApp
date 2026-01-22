from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone

from operation.models import (
    FuelLoadOperation,
    ModifyFunds,
    BalanceRechargeRequest,
    PaymentMethod,
)
from operation.serializers import (
    FuelLoadOperationSerializer,
    ModifyFundsSerializer,
    BalanceRechargeRequestCreateSerializer,
    BalanceRechargeRequestListSerializer,
    BalanceRechargeRequestDetailSerializer,
    BalanceRechargeRequestApprovalSerializer,
)
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
            ModifyFunds.objects.select_related(
                "account__user", "gestor", "payment_method"
            )
            .all()
            .order_by("-timestamp")
        )


class BalanceRechargeRequestViewSet(viewsets.ModelViewSet):
    """
    API endpoint for balance recharge requests.

    - Users can create and view their own requests
    - Gestores/Admins can view all requests and approve/reject them
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return BalanceRechargeRequestCreateSerializer
        elif self.action == "retrieve":
            return BalanceRechargeRequestDetailSerializer
        elif self.action in ["approve", "reject"]:
            return BalanceRechargeRequestApprovalSerializer
        return BalanceRechargeRequestListSerializer

    def get_queryset(self):
        """
        Users see only their own requests.
        Gestores/Admins see all requests.
        """
        user = self.request.user
        queryset = BalanceRechargeRequest.objects.select_related(
            "account__user", "requested_by", "reviewed_by"
        ).all()

        # Check if user is admin/gestor
        is_admin = (
            user.is_staff
            or user.is_superuser
            or user.groups.filter(name__in=IsAdminRole.admin_groups).exists()
        )

        if not is_admin:
            # Regular users only see their own requests
            queryset = queryset.filter(requested_by=user)

        # Optional filters
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        account_id = self.request.query_params.get("account")
        if account_id:
            queryset = queryset.filter(account_id=account_id)

        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def approve(self, request, pk=None):
        """Approve a recharge request and add funds to account"""
        recharge_request = self.get_object()

        if not recharge_request.is_pending:
            return Response(
                {"error": "Solo se pueden aprobar solicitudes pendientes"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review_comments = serializer.validated_data["review_comments"]

        try:
            with transaction.atomic():
                # Update request status
                recharge_request.status = BalanceRechargeRequest.STATUS_APPROVED
                recharge_request.reviewed_by = request.user
                recharge_request.reviewed_at = timezone.now()
                recharge_request.review_comments = review_comments
                recharge_request.save()

                # Get or create PaymentMethod for bank transfer
                payment_method, _ = PaymentMethod.objects.get_or_create(
                    name="Transferencia Bancaria", defaults={"is_active": True}
                )

                # Create ModifyFunds entry
                ModifyFunds.objects.create(
                    account=recharge_request.account,
                    gestor=request.user,
                    amount=recharge_request.amount,
                    payment_method=payment_method,
                    comments=f"Recarga aprobada. Solicitud #{recharge_request.id}. {review_comments}",
                )

                # Update account balance
                account = recharge_request.account
                account.balance += recharge_request.amount
                account.save()

            return Response(
                {
                    "message": "Solicitud aprobada exitosamente",
                    "request_id": recharge_request.id,
                    "new_balance": float(account.balance),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Error al aprobar la solicitud: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], permission_classes=[IsAdminRole])
    def reject(self, request, pk=None):
        """Reject a recharge request"""
        recharge_request = self.get_object()

        if not recharge_request.is_pending:
            return Response(
                {"error": "Solo se pueden rechazar solicitudes pendientes"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review_comments = serializer.validated_data["review_comments"]

        try:
            recharge_request.status = BalanceRechargeRequest.STATUS_REJECTED
            recharge_request.reviewed_by = request.user
            recharge_request.reviewed_at = timezone.now()
            recharge_request.review_comments = review_comments
            recharge_request.save()

            return Response(
                {"message": "Solicitud rechazada", "request_id": recharge_request.id},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Error al rechazar la solicitud: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
