from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from users.models import CustomUser
from accounts.models import Account

class Command(BaseCommand):
    help = 'Assigns the Flota role to all users who have an active account (holder or dependent)'

    def handle(self, *args, **kwargs):
        try:
            fleet_group = Group.objects.get(name='Flota')
        except Group.DoesNotExist:
            self.stdout.write(self.style.ERROR("The 'Flota' group does not exist. Please run migrations first."))
            return

        # Find users with at least one active account
        # We look for users who are linked to an Account object
        users_with_accounts = CustomUser.objects.filter(account__is_active=True).distinct()

        self.stdout.write(f"Found {users_with_accounts.count()} users with active accounts.")
        
        count = 0
        for user in users_with_accounts:
            if not user.groups.filter(name='Flota').exists():
                user.groups.add(fleet_group)
                count += 1
                self.stdout.write(f"Assigned 'Flota' role to {user.email}")
        
        self.stdout.write(self.style.SUCCESS(f"Successfully assigned 'Flota' role to {count} users."))
