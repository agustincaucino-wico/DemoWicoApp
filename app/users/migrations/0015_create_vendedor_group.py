from django.db import migrations


def create_vendedor_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Vendedor')


def remove_vendedor_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Vendedor').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0014_sync_roles'),
    ]

    operations = [
        migrations.RunPython(create_vendedor_group, remove_vendedor_group),
    ]
