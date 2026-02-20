from myapp.permissions import StrictDjangoModelPermissions
from rest_framework.permissions import BasePermission


class IsMarketingOrGestor(BasePermission):
    """
    Permission that allows access to users in Marketing or Gestor groups,
    or staff/superuser.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Staff and superuser always have access
        if request.user.is_staff or request.user.is_superuser:
            return True

        # Check if user belongs to Marketing or Gestor group
        return request.user.groups.filter(name__in=["Marketing", "Gestor"]).exists()


class DjangoModelOrTargetUser(StrictDjangoModelPermissions):
    """
    Custom permission:
    - Django's model permission level (with view_* required for GET).
    - Users can view/change/delete their own user object.
    - Everyone can create a user.
    """

    def has_permission(self, request, view):
        # Allow anyone to create (POST)
        if view.action == "create":
            return True
        # For detail actions (retrieve, update, partial_update),
        # allow authenticated users through has_permission so has_object_permission
        # can check if they're accessing their own profile
        if view.action in ["retrieve", "update", "partial_update"]:
            return request.user and request.user.is_authenticated
        # Otherwise, use default StrictDjangoModelPermissions
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        # Allow users to view/change their own user object
        if request.user.is_authenticated and obj == request.user:
            return True
        # For other users' objects, check model permissions
        # Since we bypassed has_permission() for detail actions,
        # we need to verify model permissions here
        return super().has_permission(request, view)


class DjangoModelPermissionsOrOwner(StrictDjangoModelPermissions):
    """
    Custom permission:
    - Django's model permission level (with view_* required for GET).
    - Users can change their own settings object.
    """

    def has_object_permission(self, request, view, obj):
        # Allow users to change their own settings object
        if request.user.is_authenticated and obj == request.user.setting:
            return True
        # Otherwise, use default StrictDjangoModelPermissions
        return super().has_object_permission(request, view, obj)
