from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import PromotionCode, PromotionRedemption
from myapp.admin import my_admin_site


@admin.register(PromotionCode, site=my_admin_site)
class PromotionCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "action_type",
        "status_badge",
        "valid_from",
        "valid_to",
        "usage_info",
        "redemption_count",
        "created_at",
    ]
    list_filter = ["active", "action_type", "created_at", "valid_from", "valid_to"]
    search_fields = ["code", "description"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "redemption_count",
        "validity_status",
        "usage_status",
    ]
    fieldsets = (
        (
            "Información del Código",
            {
                "fields": (
                    "code",
                    "description",
                    "active",
                    "action_type",
                    "action_params",
                    "max_uses",
                    "valid_from",
                    "valid_to",
                    "usage_status",
                    "validity_status",
                    "redemption_count",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    date_hierarchy = "created_at"
    actions = ["activate_codes", "deactivate_codes"]

    def status_badge(self, obj):
        """Muestra un badge visual del estado del código"""
        if obj.is_valid():
            color = "green"
            text = "✓ Activo"
        else:
            color = "red"
            text = "✗ Inactivo"

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            text,
        )

    status_badge.short_description = "Estado"

    def usage_info(self, obj):
        """Muestra información de uso del código"""
        current = obj.get_current_uses()
        if obj.max_uses is None:
            return format_html(
                '<span style="color: green;">🔄 Ilimitado</span>', current
            )
        else:
            remaining = obj.max_uses - current
            color = "green" if remaining > 0 else "red"
            return format_html(
                '<span style="color: {};">📊 {} / {} usos</span>',
                color,
                current,
                obj.max_uses,
            )

    usage_info.short_description = "Usos"

    def usage_status(self, obj):
        """Muestra el estado detallado de uso"""
        current = obj.get_current_uses()
        if obj.max_uses is None:
            return format_html(
                '<span style="color: green;">✅ Usos ilimitados<br>📈 Canjeado {} veces</span>',
                current,
            )
        else:
            remaining = obj.max_uses - current
            if remaining > 0:
                return format_html(
                    '<span style="color: green;">✅ {} usos disponibles<br>📊 {} de {} canjeados</span>',
                    remaining,
                    current,
                    obj.max_uses,
                )
            else:
                return format_html(
                    '<span style="color: red;">❌ Límite alcanzado<br>📊 {} de {} canjeados</span>',
                    current,
                    obj.max_uses,
                )

    usage_status.short_description = "Estado de Uso"

    def validity_status(self, obj):
        """Muestra el estado de validez detallado"""
        now = timezone.now()
        status_parts = []

        if not obj.active:
            status_parts.append("❌ Desactivado manualmente")
        else:
            status_parts.append("✅ Activado")

        return format_html("<br>".join(status_parts))

    validity_status.short_description = "Estado de Validez"

    def redemption_count(self, obj):
        """Muestra el número de canjes realizados"""
        count = obj.redemptions.count()
        return format_html(
            '<strong style="color: {};">{}</strong>',
            "green" if count > 0 else "gray",
            count,
        )

    redemption_count.short_description = "Canjes"

    def activate_codes(self, request, queryset):
        """Activa códigos seleccionados"""
        updated = queryset.update(active=True)
        self.message_user(request, f"{updated} código(s) activado(s) exitosamente.")

    activate_codes.short_description = "Activar códigos seleccionados"

    def deactivate_codes(self, request, queryset):
        """Desactiva códigos seleccionados"""
        updated = queryset.update(active=False)
        self.message_user(request, f"{updated} código(s) desactivado(s) exitosamente.")

    deactivate_codes.short_description = "Desactivar códigos seleccionados"


@admin.register(PromotionRedemption, site=my_admin_site)
class PromotionRedemptionAdmin(admin.ModelAdmin):
    list_display = ["user", "promotion_code", "amount_display", "redeemed_at"]
    list_filter = ["redeemed_at", "promotion_code__action_type"]
    search_fields = [
        "user__email",
        "user__first_name",
        "user__last_name",
        "promotion_code__code",
    ]
    readonly_fields = ["user", "promotion_code", "amount_gifted", "redeemed_at"]
    fieldsets = (
        (
            "Información del Canje",
            {"fields": ("user", "promotion_code", "amount_gifted", "redeemed_at")},
        ),
    )
    date_hierarchy = "redeemed_at"

    def amount_display(self, obj):
        """Muestra el monto regalado si aplica"""
        if obj.amount_gifted:
            formatted_amount = f"${obj.amount_gifted:.2f}"
            return format_html(
                '<span style="color: green; font-weight: bold;">{}</span>',
                formatted_amount,
            )
        return "-"

    amount_display.short_description = "Saldo Regalado"

    def has_add_permission(self, request):
        """No permitir agregar canjes manualmente desde el admin"""
        return False

    def has_change_permission(self, request, obj=None):
        """No permitir editar canjes"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Permitir eliminar canjes solo con permisos de superusuario"""
        return request.user.is_superuser
