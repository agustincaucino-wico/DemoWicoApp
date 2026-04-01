from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from users.roles import ROLES


class Command(BaseCommand):
    help = "Create default roles and assign permissions"

    def handle(self, *args, **options):
        for role_name, perms in ROLES.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created role: {role_name}"))
            else:
                self.stdout.write(f"Updating role: {role_name}")

            group.permissions.clear()  # reset before re-adding

            for perm_codename in perms:
                found = Permission.objects.filter(codename=perm_codename)
                if found.exists():
                    group.permissions.add(*found)
                else:
                    self.stdout.write(
                        self.style.WARNING(f"Permission {perm_codename} not found")
                    )

        self.stdout.write(self.style.SUCCESS("Roles setup completed ✅"))
