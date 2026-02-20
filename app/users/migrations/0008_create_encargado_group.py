from django.db import migrations


def create_encargado_group(apps, schema_editor):
    """
    Crea el grupo 'Encargado' en auth_group.
    """
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Encargado")


def remove_encargado_group(apps, schema_editor):
    """
    Elimina el grupo 'Encargado' de auth_group (para rollback).
    """
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Encargado").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0007_passwordresettoken"),
    ]

    operations = [
        migrations.RunPython(create_encargado_group, remove_encargado_group),
    ]
