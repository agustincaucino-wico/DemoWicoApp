from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0019_remove_authorizedemail_unique_pending_authorized_email_and_more",
        ),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="authorizedemail",
            name="unique_authorized_email_per_status",
        ),
    ]
