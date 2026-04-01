"""
Data migration to sync roles after adding Organism and AuthorizedEmail
permissions to ROLES.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from users.roles import ROLES


def setup_roles(apps, schema_editor):
    for app_config in apps.app_configs.values():
        app_config.models_module = getattr(app_config, "models_module", True)
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for role_name, perm_codenames in ROLES.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.clear()

        missing = []
        for codename in perm_codenames:
            perms = Permission.objects.filter(codename=codename)
            if perms.exists():
                group.permissions.add(*perms)
            else:
                missing.append(codename)

        if missing:
            print(
                f"[sync_roles] WARNING: role '{role_name}' – "
                f"permissions not found: {missing}"
            )


def teardown_roles(apps, schema_editor):
    pass  # no-op: no revertimos cambios de permisos


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0013_sync_roles"),
        ("accounts", "0018_authorizedemail"),
    ]

    operations = [
        migrations.RunPython(setup_roles, reverse_code=teardown_roles),
    ]
