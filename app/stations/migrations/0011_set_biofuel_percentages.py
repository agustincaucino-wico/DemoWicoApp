from django.db import migrations

BIOFUEL_PERCENTAGES = {
    "B20": 20.00,
    "E17": 17.00,
    "GO LS": 12.00,
    "GO PLUS": 12.00,
    "NAFTA PLUS": 7.50,
    "NAFTA SUPER": 7.50,
}


def set_biofuel_percentages(apps, schema_editor):
    FuelType = apps.get_model("stations", "FuelType")
    for name, percentage in BIOFUEL_PERCENTAGES.items():
        FuelType.objects.filter(name=name).update(biofuel_percentage=percentage)


def unset_biofuel_percentages(apps, schema_editor):
    FuelType = apps.get_model("stations", "FuelType")
    FuelType.objects.filter(name__in=BIOFUEL_PERCENTAGES.keys()).update(
        biofuel_percentage=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("stations", "0010_add_biofuel_percentage_to_fueltype"),
    ]

    operations = [
        migrations.RunPython(set_biofuel_percentages, unset_biofuel_percentages),
    ]
