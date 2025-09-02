from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import CustomUser, Role, RolAssignment, Setting
from myapp.admin import my_admin_site
from django.contrib import admin


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = (
        "id",
        "email",
        "dni",
        "first_name",
        "last_name",
        "phone_number",
        "is_authorized_holder",
        "is_staff",
        "is_superuser",
    )
    search_fields = ("email", "dni", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            ("Personal Info"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "dni",
                    "phone_number",
                    "id_province",
                )
            },
        ),
        (
            ("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_authorized_holder",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (("Important Dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "dni",
                    "first_name",
                    "last_name",
                    "phone_number",
                    "id_province",
                    "is_authorized_holder",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                ),
            },
        ),
    )


my_admin_site.register([Role, RolAssignment, Setting])
my_admin_site.register(CustomUser, CustomUserAdmin)
