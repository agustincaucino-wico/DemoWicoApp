from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsManagerOrOwner(BasePermission):
    """
    Permiso personalizado:
    - Los gestores (is_staff) tienen acceso total (GET, POST, DELETE)
    - Los usuarios regulares solo pueden crear reportes (POST) y ver los suyos (GET)
    - Los usuarios regulares solo pueden eliminar sus propios reportes
    """

    def has_permission(self, request, view):
        # Usuarios autenticados pueden crear reportes
        if request.method == "POST":
            return request.user and request.user.is_authenticated

        # Gestores tienen acceso total
        if request.user and request.user.is_staff:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        # Gestores tienen acceso total
        if request.user and request.user.is_staff:
            return True
