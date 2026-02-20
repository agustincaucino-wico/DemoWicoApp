# Generated migration to remove Cliente role from the system

from django.db import migrations


def remove_cliente_role(apps, schema_editor):
    """
    Remove the Cliente group from all users and delete it from the system.
    """
    Group = apps.get_model("auth", "Group")

    # Get the Cliente group if it exists
    try:
        cliente_group = Group.objects.get(name="Cliente")

        # Remove the group from all users who have it
        cliente_group.user_set.clear()

        # Delete the group
        cliente_group.delete()

        print(
            f"Successfully removed Cliente role from all users and deleted the group."
        )
    except Group.DoesNotExist:
        print("Cliente group does not exist, nothing to remove.")


def reverse_remove_cliente_role(apps, schema_editor):
    """
    Reverse migration: recreate the Cliente group.
    Note: This does not restore the group to users who previously had it.
    """
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    # Recreate the Cliente group
    cliente_group, created = Group.objects.get_or_create(name="Cliente")

    if created:
        # Add permissions back to the group
        permission_codenames = [
            "view_city",
            "view_province",
            "view_country",
        ]

        for codename in permission_codenames:
            try:
                permission = Permission.objects.get(codename=codename)
                cliente_group.permissions.add(permission)
            except Permission.DoesNotExist:
                print(f"Permission {codename} does not exist, skipping.")

        print("Cliente group recreated with permissions.")
    else:
        print("Cliente group already exists.")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0010_create_fleet_group"),
    ]

    operations = [
        migrations.RunPython(
            remove_cliente_role,
            reverse_code=reverse_remove_cliente_role,
        ),
    ]
