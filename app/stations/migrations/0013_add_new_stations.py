from django.db import migrations


STATIONS = [
    {
        "name": "Isabel la Católica",
        "street": "Isabel la Católica",
        "street_number": "1276",
        "lat": "-31.387309",
        "lon": "-64.190359",
    },
    {
        "name": "Cofico",
        "street": "José Maria Bedoya",
        "street_number": "701",
        "lat": "-31.398048",
        "lon": "-64.186996",
    },
    {
        "name": "Pavone",
        "street": "General Bernardo O'Higgins",
        "street_number": "3026",
        "lat": "-31.446942",
        "lon": "-64.169316",
    },
]


def add_stations(apps, schema_editor):
    Station = apps.get_model("stations", "Station")
    Province = apps.get_model("locations", "Province")
    City = apps.get_model("locations", "City")

    try:
        province = Province.objects.get(name="Córdoba")
        city = City.objects.get(name="Córdoba", province=province)
    except (Province.DoesNotExist, City.DoesNotExist):
        # En entornos de test la provincia/ciudad de referencia no existe aún;
        # se omite la carga de datos sin error.
        return

    for data in STATIONS:
        Station.objects.get_or_create(
            name=data["name"],
            street=data["street"],
            street_number=data["street_number"],
            city=city,
            defaults={
                "province": province,
                "lat": data["lat"],
                "lon": data["lon"],
                "expendio": "cordoba",
                "is_active": True,
            },
        )


def remove_stations(apps, schema_editor):
    Station = apps.get_model("stations", "Station")
    names = [s["name"] for s in STATIONS]
    Station.objects.filter(name__in=names, expendio="cordoba").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("stations", "0012_station_expendio_choices"),
        ("locations", "__latest__"),
    ]

    operations = [
        migrations.RunPython(add_stations, remove_stations),
    ]
