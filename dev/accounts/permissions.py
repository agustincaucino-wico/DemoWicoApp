from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.permissions import DjangoModelPermissions


class IsAdminOrReadOnly(BasePermission):
    """
    Allows access only to admin users for unsafe methods, read-only for others.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class DjangoModelOrPlatesOwner(DjangoModelPermissions):
    """
    Custom permission:
    - Django's model permission level.
    - Account holders can view/change/delete their own plates and authorized plates.
    - Dependent's account holders can view the authorized plates linked to their accounts.
    """

    # def has_permission(self, request, view):
    #     # Allow anyone to create (POST)
    #     if view.action == "create":
    #         return True
    #     # Otherwise, use default DjangoModelPermissions
    #     return super().has_permission(request, view)

    # def has_object_permission(self, request, view, obj):
    #     # Allow account holders to view/change/delete their own plates and authorized plates
    #     if request.user.is_authenticated:
    #         user_accounts = request.user.account_set.all()
    #         if hasattr(obj, "holder_account"):
    #             if obj.holder_account in user_accounts:
    #                 return True
    #         elif hasattr(obj, "authorized_plate"):
    #             if obj.authorized_plate.holder_account in user_accounts:
    #                 return True
    #         elif hasattr(obj, "dependent"):
    #             if obj.dependent.holder_account in user_accounts:
    #                 return True
    #     # Otherwise, use default DjangoModelPermissions
    #     return super().has_object_permission(request, view, obj)
