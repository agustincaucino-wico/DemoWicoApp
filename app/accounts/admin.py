from django.contrib import admin
from .models import (
    Account,
    Dependents,
    Plates,
    AuthorizedPlate,
    Company,
    CompanyAssignment,
    DependentInvitation,
)
from myapp.admin import my_admin_site


class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "balance", "account_type", "created_at", "updated_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("account_type", "created_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user",)


class DependentsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "holder_account",
        "dependent_account",
        "start_date",
        "end_date",
    )
    search_fields = ("holder_account__user__email", "dependent_account__user__email")
    list_filter = ("start_date", "end_date")
    autocomplete_fields = ("holder_account", "dependent_account")


class PlatesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "plate_number",
        "holder_account",
        "brand",
        "model",
        "start_date",
        "end_date",
    )
    search_fields = ("plate_number", "holder_account__user__email", "brand", "model")
    list_filter = ("start_date", "end_date")
    autocomplete_fields = ("holder_account",)


class AuthorizedPlateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "holder_account",
        "dependent_account",
        "plate",
        "start_date",
        "end_date",
    )
    search_fields = (
        "dependent_account__user__email",
        "plate__plate_number",
    )
    list_filter = ("start_date", "end_date")
    autocomplete_fields = ("dependent_account", "plate")

    def holder_account(self, obj):
        return obj.plate.holder_account if obj.plate else None

    holder_account.short_description = "Cuenta Titular de la Patente"


class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "province")
    search_fields = ("name", "province__name")
    list_filter = ("province",)
    autocomplete_fields = ("province",)


class CompanyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "company", "start_date", "end_date")
    search_fields = ("user__email", "company__name")
    list_filter = ("company", "start_date", "end_date")
    autocomplete_fields = ("user", "company")


class DependentInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "holder_account_email",
        "dependent_email",
        "status",
        "invitation_date",
        "response_date",
    )
    search_fields = ("holder_account__user__email", "dependent_email")
    list_filter = ("status", "invitation_date", "response_date")
    readonly_fields = ("invitation_date", "response_date")
    autocomplete_fields = ("holder_account",)

    def holder_account_email(self, obj):
        return (
            obj.holder_account.user.email
            if obj.holder_account and obj.holder_account.user
            else None
        )

    holder_account_email.short_description = "Email Cuenta Titular"


my_admin_site.register(Account, AccountAdmin)
my_admin_site.register(Dependents, DependentsAdmin)
my_admin_site.register(Plates, PlatesAdmin)
my_admin_site.register(AuthorizedPlate, AuthorizedPlateAdmin)
my_admin_site.register(Company, CompanyAdmin)
my_admin_site.register(CompanyAssignment, CompanyAssignmentAdmin)
my_admin_site.register(DependentInvitation, DependentInvitationAdmin)
