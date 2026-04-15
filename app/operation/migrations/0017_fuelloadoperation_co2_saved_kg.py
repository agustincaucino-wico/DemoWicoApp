from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation", "0016_move_fueltype_fk_to_stations"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelloadoperation",
            name="co2_saved_kg",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Emisiones totales evitadas en kgCO2e. Calculado según el tipo de biocombustible.",
                max_digits=10,
                null=True,
                verbose_name="CO₂ evitado (kgCO2e)",
            ),
        ),
    ]
