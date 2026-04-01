from rest_framework.permissions import BasePermission, SAFE_METHODS
from myapp.permissions import StrictDjangoModelPermissions
from users.utils import should_apply_flota_restrictions


class IsAdminOrReadOnly(BasePermission):
    """
    Allows access only to admin users for unsafe methods, read-only for others.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class IsPlayero(BasePermission):
    """
    Permite acceso solo a usuarios con rol de Playero.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="Playero").exists()
        )


class DjangoModelOrObjectOwner(StrictDjangoModelPermissions):
    """
    Custom permission:
    - Django's model permission level (with view_* required for GET).
    - Account holders can view/change/delete their own plates and authorized plates.
    - Dependent's account holders can view the authorized plates linked to their accounts.
    - Users with 'Flota' role (sin rol Gestor) can manage their own plates and authorized plates.
    - Users with 'Gestor' role have full access regardless of Flota role.
    """

    def has_permission(self, request, view):
        # Allow users with 'Flota' group (but not Gestor) to perform CRUD operations on their own resources
        if request.user.is_authenticated and should_apply_flota_restrictions(
            request.user
        ):
            # Flota users can perform all operations on Plates, AuthorizedPlate, Dependents
            model_name = getattr(view, "queryset", None)
            if model_name is not None:
                model_name = model_name.model.__name__
                if model_name in [
                    "Plates",
                    "AuthorizedPlate",
                    "Dependents",
                    "Account",
                    "AuthorizedEmail",
                ]:
                    return True

        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        # Allow account holders to view/change/delete their own plates and authorized plates
        if request.user.is_authenticated:
            user_accounts = request.user.account_set.all()

            # Plates: objects with a holder_account attribute (e.g. Plates)
            # Exclude Dependents which also have holder_account/dependent_account pair above
            if hasattr(obj, "holder_account") and not hasattr(obj, "dependent_account"):
                if obj.holder_account in user_accounts:
                    return True

            # AuthorizedPlate objects: have 'plate' and 'dependent_account' attributes
            if hasattr(obj, "plate") and hasattr(obj, "dependent_account"):
                plate_holder = getattr(
                    getattr(obj, "plate", None), "holder_account", None
                )
                if plate_holder and plate_holder in user_accounts:
                    return True

            # Dependents
            if hasattr(obj, "holder_account") and hasattr(obj, "dependent_account"):
                if obj.holder_account in user_accounts:
                    return True

            # Account objects: allow access to user's own accounts
            if hasattr(obj, "user") and getattr(obj, "user") == request.user:
                return True

            # AuthorizedEmail: allow access if dependent_of is a holder account of the user
            if hasattr(obj, "dependent_of"):
                if obj.dependent_of in user_accounts:
                    return True

        # Otherwise, use default StrictDjangoModelPermissions
        return super().has_object_permission(request, view, obj)
