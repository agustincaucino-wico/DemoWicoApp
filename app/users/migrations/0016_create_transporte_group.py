from django.db import migrations


def create_transporte_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Transporte')


def remove_transporte_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Transporte').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_create_vendedor_group'),
    ]

    operations = [
        migrations.RunPython(create_transporte_group, remove_transporte_group),
    ]
