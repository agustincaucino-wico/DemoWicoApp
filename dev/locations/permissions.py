from rest_framework.permissions import BasePermission

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class IsAdminOrReadOnly(BasePermission):
    """
    The request is allowed if it is a read-only request (GET, HEAD, OPTIONS)
    or if the user is a staff member.
    """

    def has_permission(self, request, view):
        return bool(
            request.method in SAFE_METHODS
            or (
                request.user and request.user.is_authenticated and request.user.is_staff
            )
        )
