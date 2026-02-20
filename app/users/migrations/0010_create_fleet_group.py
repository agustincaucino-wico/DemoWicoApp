from django.db import migrations

def create_fleet_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Flota')

def remove_fleet_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Flota').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_customuser_email_verified_emailverificationtoken'),
    ]

    operations = [
        migrations.RunPython(create_fleet_group, remove_fleet_group),
    ]
