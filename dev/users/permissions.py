from rest_framework import permissions


class DjangoModelOrTargetUser(permissions.DjangoModelPermissions):
    """
    Custom permission:
    - Django's model permission level.
    - Users can view/change/delete their own user object.
    - Everyone can create a user.
    """

    def has_permission(self, request, view):
        # Allow anyone to create (POST)
        if view.action == "create":
            return True
        # Otherwise, use default DjangoModelPermissions
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        # Allow users to view/change/delete their own user object
        if request.user.is_authenticated and obj == request.user:
            return True
        # Otherwise, use default DjangoModelPermissions
        return super().has_object_permission(request, view, obj)


class DjangoModelPermissionsOrOwner(permissions.DjangoModelPermissions):
    """
    Custom permission:
    - Django's model permission level.
    - Users can change their own settings object.
    """

    def has_object_permission(self, request, view, obj):
        # Allow users to change their own settings object
        if request.user.is_authenticated and obj == request.user.setting:
            return True
        # Otherwise, use default DjangoModelPermissions
        return super().has_object_permission(request, view, obj)
