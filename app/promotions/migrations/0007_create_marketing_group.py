# Generated manually

from django.db import migrations


def create_marketing_group(apps, schema_editor):
    """Create Marketing group with permissions to manage promotional images"""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    # Get or create Marketing group
    marketing_group, created = Group.objects.get_or_create(name="Marketing")

    if created:
        print("Created Marketing group")

    # Get PromotionalImage content type
    try:
        promotional_image_ct = ContentType.objects.get(
            app_label="promotions", model="promotionalimage"
        )

        # Get all permissions for PromotionalImage
        permissions = Permission.objects.filter(content_type=promotional_image_ct)

        # Add permissions to Marketing group
        marketing_group.permissions.add(*permissions)

        print(f"Added {permissions.count()} permissions to Marketing group")
    except ContentType.DoesNotExist:
        print(
            "PromotionalImage content type not found - permissions will need to be added manually"
        )


def reverse_marketing_group(apps, schema_editor):
    """Remove Marketing group"""
    Group = apps.get_model("auth", "Group")

    try:
        marketing_group = Group.objects.get(name="Marketing")
        marketing_group.delete()
        print("Removed Marketing group")
    except Group.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0006_promotionalimage"),
    ]

    operations = [
        migrations.RunPython(create_marketing_group, reverse_marketing_group),
    ]
