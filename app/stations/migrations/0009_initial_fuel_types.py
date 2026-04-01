from django.db import migrations


def create_fuel_types(apps, schema_editor):
    FuelType = apps.get_model("stations", "FuelType")
    fuel_types = ["E17", "B20", "GO LS", "GO PLUS", "NAFTA PLUS", "NAFTA SUPER"]
    for name in fuel_types:
        FuelType.objects.get_or_create(name=name, defaults={"is_active": True})


def delete_fuel_types(apps, schema_editor):
    FuelType = apps.get_model("stations", "FuelType")
    FuelType.objects.filter(
        name__in=["E17", "B20", "GO LS", "GO PLUS", "NAFTA PLUS", "NAFTA SUPER"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("stations", "0008_fueltype_fueltypeprice"),
    ]

    operations = [
        migrations.RunPython(create_fuel_types, delete_fuel_types),
    ]
