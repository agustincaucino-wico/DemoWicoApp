"""
Shared test helpers for assigning roles (Group + Permissions) to users.
"""

from django.contrib.auth.models import Group, Permission

from .roles import ROLES


class RoleAssignmentMixin:
    """Mixin providing a helper to assign a ROLES-based Group to a user in tests."""

    def assign_role(self, user, role_name):
        group, _ = Group.objects.get_or_create(name=role_name)
        permissions = Permission.objects.filter(codename__in=ROLES.get(role_name, []))
        group.permissions.set(permissions)
        user.groups.add(group)
