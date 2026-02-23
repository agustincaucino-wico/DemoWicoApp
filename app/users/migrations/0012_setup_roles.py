"""
Data migration that creates Groups and assigns permissions as defined in
users/roles.py. It runs automatically on every `migrate`, but is idempotent:
  - Groups are created only if they do not already exist.
  - Permissions are reset to match the current ROLES definition each time,
    so adding/removing permissions in roles.py + running migrate is enough.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from users.roles import ROLES


def setup_roles(apps, schema_editor):
    # Permissions are created by the post_migrate signal, which fires AFTER all
    # migrations finish. When this migration runs, they may not exist yet.
    # We force-create them here using the same historical app registry so that
    # everything stays consistent.
    for app_config in apps.app_configs.values():
        app_config.models_module = getattr(app_config, "models_module", True)
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for role_name, perm_codenames in ROLES.items():
        group, _ = Group.objects.get_or_create(name=role_name)

        # Reset permissions to match the current definition exactly
        group.permissions.clear()

        missing = []
        for codename in perm_codenames:
            try:
                perm = Permission.objects.get(codename=codename)
                group.permissions.add(perm)
            except Permission.DoesNotExist:
                missing.append(codename)

        if missing:
            print(
                f"[setup_roles] WARNING: role '{role_name}' – "
                f"permissions not found: {missing}"
            )


def teardown_roles(apps, schema_editor):
    """Reverse: remove only the groups defined in ROLES (leaves others intact)."""
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES.keys()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0011_remove_cliente_role"),
        # auth must be fully migrated so Group/Permission tables exist
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(setup_roles, reverse_code=teardown_roles),
    ]
