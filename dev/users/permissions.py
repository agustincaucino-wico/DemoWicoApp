from rest_framework import permissions

class IsStaffOrTargetUser(permissions.BasePermission):
    """
    Custom permission:
    - Staff users can do anything.
    - Users can view/change/delete their own user object.
    """

    def has_permission(self, request, view):
        # Allow anyone to create (POST)
        if view.action == 'create':
            return True
        # Only staff can list all users
        if view.action == 'list':
            return request.user and request.user.is_staff
        # For retrieve/update/destroy, check object permissions
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Staff can do anything
        if request.user.is_staff:
            return True
        # Users can access/change/delete their own user object
        return obj == request.user