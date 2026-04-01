from django.db import migrations


def create_organism(apps, schema_editor):
    Organism = apps.get_model("accounts", "Organism")
    Organism.objects.get_or_create(
        name="Gobierno de Córdoba",
        defaults={"cuit": "30-67869994-9", "billing_type": "invoice"},
    )


def delete_organism(apps, schema_editor):
    Organism = apps.get_model("accounts", "Organism")
    Organism.objects.filter(name="Gobierno de Córdoba").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_account_special_account_unlimited_balance"),
    ]

    operations = [
        migrations.RunPython(create_organism, delete_organism),
    ]
