from rest_framework.permissions import SAFE_METHODS
from myapp.permissions import StrictDjangoModelPermissions


class AuthenticatedReadDjangoModelPermissions(StrictDjangoModelPermissions):
    """Allow authenticated users to read while enforcing model perms for writes."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return super().has_permission(request, view)
