from django.contrib import admin
from django.utils import timezone
from django.contrib import messages

from myapp.admin import my_admin_site
from operation.models import (
    FuelLoadOperation,
    PaymentMethod,
    Transfer,
    BalanceRechargeRequest,
    ModifyFunds,
)
from utils.email_service import email_service


@admin.register(PaymentMethod, site=my_admin_site)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(FuelLoadOperation, site=my_admin_site)
class FuelLoadOperationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account",
        "plate",
        "station",
        "attendant",
        "initial_amount",
        "final_amount",
        "fill_full_tank",
        "status",
        "payment_method",
        "timestamp_started",
        "timestamp_atended",
        "timestamp_finished",
    )
    list_filter = ("status", "fill_full_tank", "payment_method", "timestamp_started")
    search_fields = (
        "account__user__email",
        "plate__plate_number",
        "station__name",
        "attendant__email",
    )
    autocomplete_fields = ("account", "plate", "attendant", "station", "payment_method")


@admin.register(Transfer, site=my_admin_site)
class TransferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_account",
        "destination_account",
        "amount",
        "timestamp",
    )
    list_filter = ("timestamp",)
    search_fields = (
        "source_account__user__email",
        "destination_account__user__email",
    )
    autocomplete_fields = ("source_account", "destination_account")
    readonly_fields = ("timestamp",)


@admin.register(BalanceRechargeRequest, site=my_admin_site)
class BalanceRechargeRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account",
        "requested_by",
        "amount",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = (
        "status",
        "created_at",
        "reviewed_at",
    )
    search_fields = (
        "account__user__email",
        "requested_by__email",
        "reviewed_by__email",
    )
    autocomplete_fields = ("account", "requested_by", "reviewed_by")
    readonly_fields = (
        "created_at",
        "updated_at",
        "reviewed_at",
    )
    fieldsets = (
        (
            "Información de la Solicitud",
            {
                "fields": (
                    "account",
                    "requested_by",
                    "amount",
                    "transfer_proof",
                    "comments",
                )
            },
        ),
        (
            "Estado",
            {
                "fields": (
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "review_comments",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["approve_requests", "reject_requests"]

    def approve_requests(self, request, queryset):
        """Bulk approve selected requests"""
        pending_requests = queryset.filter(status=BalanceRechargeRequest.STATUS_PENDING)
        count = pending_requests.count()

        if count == 0:
            self.message_user(
                request,
                "No hay solicitudes pendientes para aprobar",
                level=messages.WARNING,
            )
            return

        # Get or create payment method
        payment_method, _ = PaymentMethod.objects.get_or_create(
            name="Transferencia Bancaria", defaults={"is_active": True}
        )

        for recharge_request in pending_requests:
            # Update request
            recharge_request.status = BalanceRechargeRequest.STATUS_APPROVED
            recharge_request.reviewed_by = request.user
            recharge_request.reviewed_at = timezone.now()
            recharge_request.review_comments = "Aprobado desde admin panel"
            recharge_request.save()

            # Create ModifyFunds
            ModifyFunds.objects.create(
                account=recharge_request.account,
                gestor=request.user,
                amount=recharge_request.amount,
                payment_method=payment_method,
                comments=f"Recarga aprobada. Solicitud #{recharge_request.id}",
            )

            # Update balance
            account = recharge_request.account
            account.balance += recharge_request.amount
            account.save()

            # Send approval email notification
            user = recharge_request.requested_by
            user_name = user.get_full_name() or user.email
            email_service.send_balance_recharge_approved(
                to_email=user.email,
                user_name=user_name,
                amount=recharge_request.amount,
                new_balance=account.balance,
                request_id=recharge_request.id,
            )

        self.message_user(
            request,
            f"Se aprobaron {count} solicitudes exitosamente",
            level=messages.SUCCESS,
        )

    approve_requests.short_description = "Aprobar solicitudes seleccionadas"

    def reject_requests(self, request, queryset):
        """Bulk reject selected requests"""
        pending_requests = queryset.filter(status=BalanceRechargeRequest.STATUS_PENDING)

        rejection_reason = "Rechazado desde admin panel"

        for recharge_request in pending_requests:
            # Update request
            recharge_request.status = BalanceRechargeRequest.STATUS_REJECTED
            recharge_request.reviewed_by = request.user
            recharge_request.reviewed_at = timezone.now()
            recharge_request.review_comments = rejection_reason
            recharge_request.save()

            # Send rejection email notification
            user = recharge_request.requested_by
            user_name = user.get_full_name() or user.email
            email_service.send_balance_recharge_rejected(
                to_email=user.email,
                user_name=user_name,
                amount=recharge_request.amount,
                request_id=recharge_request.id,
                rejection_reason=recharge_request.review_comments,
            )

        count = pending_requests.count()

        self.message_user(
            request,
            f"Se rechazaron {count} solicitudes",
            level=messages.SUCCESS if count > 0 else messages.WARNING,
        )

    reject_requests.short_description = "Rechazar solicitudes seleccionadas"
