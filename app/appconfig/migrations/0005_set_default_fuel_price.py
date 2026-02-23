from django.db import migrations
from decimal import Decimal


def set_default_fuel_price(apps, schema_editor):
    AppConfig = apps.get_model("appconfig", "AppConfig")
    config, _ = AppConfig.objects.get_or_create(pk=1)
    config.fuel_price = Decimal("1928.00")
    config.save()


def unset_fuel_price(apps, schema_editor):
    AppConfig = apps.get_model("appconfig", "AppConfig")
    config = AppConfig.objects.filter(pk=1).first()
    if config:
        config.fuel_price = None
        config.save()


class Migration(migrations.Migration):
    dependencies = [
        ("appconfig", "0004_fuel_price"),
    ]

    operations = [
        migrations.RunPython(set_default_fuel_price, reverse_code=unset_fuel_price),
    ]
