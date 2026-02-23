from django.db import migrations


DEFAULT_TIERS = [
    {"min_liters": 100,   "bonus_percent": 10, "color_intensity": 1.0,  "order": 0},
    {"min_liters": 3000,  "bonus_percent": 11, "color_intensity": 0.65, "order": 1},
    {"min_liters": 5000,  "bonus_percent": 12, "color_intensity": 0.35, "order": 2},
    {"min_liters": 10000, "bonus_percent": 13, "color_intensity": 0.1,  "order": 3},
]


def seed_tiers(apps, schema_editor):
    BonificationTier = apps.get_model("appconfig", "BonificationTier")
    # Only seed if no tiers exist yet
    if not BonificationTier.objects.exists():
        for tier in DEFAULT_TIERS:
            BonificationTier.objects.create(**tier)


def unseed_tiers(apps, schema_editor):
    BonificationTier = apps.get_model("appconfig", "BonificationTier")
    BonificationTier.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("appconfig", "0006_bonificationtier"),
    ]

    operations = [
        migrations.RunPython(seed_tiers, reverse_code=unseed_tiers),
    ]
