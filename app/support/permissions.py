from myapp.permissions import StrictDjangoModelPermissions


class IsGestorOrCreateOnly(StrictDjangoModelPermissions):
    """
    Permiso para reportes de errores:
    - Cualquier usuario autenticado puede crear reportes (POST)
    - Las demás acciones requieren los permisos del modelo (Gestor)
    """

    def has_permission(self, request, view):
        # Cualquier usuario autenticado puede crear reportes
        if view.action == "create":
            return request.user and request.user.is_authenticated

        # Para las demás acciones, usar StrictDjangoModelPermissions
        return super().has_permission(request, view)
