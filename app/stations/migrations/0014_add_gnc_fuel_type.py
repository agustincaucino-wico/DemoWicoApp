from django.db import migrations


def add_gnc_fuel_type(apps, schema_editor):
    FuelType = apps.get_model("stations", "FuelType")
    FuelType.objects.get_or_create(name="GNC", defaults={"is_active": True})


def remove_gnc_fuel_type(apps, schema_editor):
    FuelType = apps.get_model("stations", "FuelType")
    FuelType.objects.filter(name="GNC").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("stations", "0013_add_new_stations"),
    ]

    operations = [
        migrations.RunPython(add_gnc_fuel_type, remove_gnc_fuel_type),
    ]