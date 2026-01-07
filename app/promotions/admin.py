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
    ]
    fieldsets = (
        ("Información Básica", {"fields": ("code", "description", "active")}),
        ("Acción", {"fields": ("action_type", "action_params")}),
        ("Validez", {"fields": ("valid_from", "valid_to", "validity_status")}),
        ("Estadísticas", {"fields": ("redemption_count",), "classes": ("collapse",)}),
        (
            "Información del Sistema",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
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

    def validity_status(self, obj):
        """Muestra el estado de validez detallado"""
        now = timezone.now()
        status_parts = []

        if not obj.active:
            status_parts.append("❌ Desactivado manualmente")
        else:
            status_parts.append("✅ Activado")

        if obj.valid_from:
            if now < obj.valid_from:
                status_parts.append(
                    f"⏳ Comienza: {obj.valid_from.strftime('%d/%m/%Y %H:%M')}"
                )
            else:
                status_parts.append(
                    f"✅ Comenzó: {obj.valid_from.strftime('%d/%m/%Y %H:%M')}"
                )

        if obj.valid_to:
            if now > obj.valid_to:
                status_parts.append(
                    f"❌ Expiró: {obj.valid_to.strftime('%d/%m/%Y %H:%M')}"
                )
            else:
                status_parts.append(
                    f"⏰ Expira: {obj.valid_to.strftime('%d/%m/%Y %H:%M')}"
                )

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
    list_display = ["user", "promotion_code", "redeemed_at"]
    list_filter = ["redeemed_at", "promotion_code__action_type"]
    search_fields = [
        "user__email",
        "user__first_name",
        "user__last_name",
        "promotion_code__code",
    ]
    readonly_fields = ["user", "promotion_code", "redeemed_at"]
    date_hierarchy = "redeemed_at"

    def has_add_permission(self, request):
        """No permitir agregar canjes manualmente desde el admin"""
        return False

    def has_change_permission(self, request, obj=None):
        """No permitir editar canjes"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Permitir eliminar canjes solo con permisos de superusuario"""
        return request.user.is_superuser
