import math
from decimal import Decimal

from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.utils import timezone

from appconfig.models import AppConfig, BonificationTier

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
from utils.email_service import email_service


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

    - Any authenticated user can create a request (POST).
    - Only Gestores/Admins can list, retrieve, approve or reject requests.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAdminRole()]

    def get_serializer_class(self):
        if self.action == "create":
            return BalanceRechargeRequestCreateSerializer
        elif self.action == "retrieve":
            return BalanceRechargeRequestDetailSerializer
        elif self.action in ["approve", "reject"]:
            return BalanceRechargeRequestApprovalSerializer
        return BalanceRechargeRequestListSerializer

    def get_queryset(self):
        """Only Gestores/Admins reach this point (create doesn't call get_queryset)."""
        queryset = BalanceRechargeRequest.objects.select_related(
            "account__user", "requested_by", "reviewed_by"
        ).all()

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

        review_comments = serializer.validated_data.get("review_comments", "")

        # Calculate applicable bonification bonus
        config = AppConfig.get_config()
        fuel_price = config.fuel_price
        bonus_amount = Decimal("0")
        applied_tier_percent = None

        if fuel_price:
            applicable_tier = None
            for (
                tier
            ) in BonificationTier.objects.all():  # ordered by order, min_liters asc
                raw_amount = tier.min_liters * fuel_price
                # Redondeo hacia abajo al millar, igual que en la UI
                min_amount = Decimal(str(math.floor(float(raw_amount) / 1000) * 1000))
                if recharge_request.amount >= min_amount:
                    applicable_tier = tier
            if applicable_tier:
                bonus_amount = (
                    recharge_request.amount
                    * applicable_tier.bonus_percent
                    / Decimal("100")
                ).quantize(Decimal("1"), rounding="ROUND_DOWN")
                applied_tier_percent = float(applicable_tier.bonus_percent)

        total_credited = recharge_request.amount + bonus_amount

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

                # Build comment including bonus info
                bonus_comment = (
                    f"Bonificación {applied_tier_percent}%" if bonus_amount > 0 else ""
                )

                # Create ModifyFunds entry with total (base + bonus)
                ModifyFunds.objects.create(
                    account=recharge_request.account,
                    gestor=request.user,
                    amount=total_credited,
                    payment_method=payment_method,
                    comments=(
                        "Recarga aprobada."
                        + (f"\n{bonus_comment}" if bonus_comment else "")
                    ),
                )

                # Update account balance with total (base + bonus)
                account = recharge_request.account
                account.balance += total_credited
                account.save()

                # Send approval email notification (non-blocking)
                try:
                    user = recharge_request.requested_by
                    user_name = user.get_full_name() or user.email
                    email_service.send_balance_recharge_approved(
                        to_email=user.email,
                        user_name=user_name,
                        amount=total_credited,
                        new_balance=account.balance,
                        request_id=recharge_request.id,
                    )
                except Exception as email_error:
                    print(f"Error al enviar email de aprobación: {email_error}")

            return Response(
                {
                    "message": "Solicitud aprobada exitosamente",
                    "request_id": recharge_request.id,
                    "new_balance": float(account.balance),
                    "bonus_amount": float(bonus_amount),
                    "applied_tier_percent": applied_tier_percent,
                    "total_credited": float(total_credited),
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

        review_comments = serializer.validated_data.get("review_comments", "")

        try:
            recharge_request.status = BalanceRechargeRequest.STATUS_REJECTED
            recharge_request.reviewed_by = request.user
            recharge_request.reviewed_at = timezone.now()
            recharge_request.review_comments = review_comments
            recharge_request.save()

            # Send rejection email notification (non-blocking)
            try:
                user = recharge_request.requested_by
                user_name = user.get_full_name() or user.email
                email_service.send_balance_recharge_rejected(
                    to_email=user.email,
                    user_name=user_name,
                    amount=recharge_request.amount,
                    request_id=recharge_request.id,
                    rejection_reason=review_comments,
                )
            except Exception as email_error:
                print(f"Error al enviar email de rechazo: {email_error}")

            return Response(
                {"message": "Solicitud rechazada", "request_id": recharge_request.id},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Error al rechazar la solicitud: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
