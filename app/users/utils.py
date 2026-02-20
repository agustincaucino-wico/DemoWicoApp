"""
Utilidades para manejo de roles y permisos de usuarios
"""


def user_has_gestor_role(user):
    """
    Verifica si un usuario tiene el rol de Gestor.

    Args:
        user: Instancia de CustomUser

    Returns:
        bool: True si el usuario tiene el rol de Gestor, False en caso contrario
    """
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name="Gestor").exists()


def should_apply_flota_restrictions(user):
    """
    Determina si se deben aplicar restricciones de Flota a un usuario.

    Si un usuario tiene ambos roles (Gestor y Flota), se aplican los permisos
    de Gestor (mayor nivel), por lo que NO se aplican restricciones de Flota.

    Args:
        user: Instancia de CustomUser

    Returns:
        bool: True si se deben aplicar restricciones de Flota, False en caso contrario
    """
    if not user or not user.is_authenticated:
        return False

    # Si tiene rol de Gestor, no aplicar restricciones de Flota
    if user_has_gestor_role(user):
        return False

    # Si tiene rol de Flota (y no tiene Gestor), aplicar restricciones
    return user.groups.filter(name="Flota").exists()
