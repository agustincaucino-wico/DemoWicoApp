from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Dependents, Account
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model


@receiver(post_save, sender=get_user_model())
def create_holder_account_on_registration(sender, instance, created, **kwargs):
    """
    Automatically create a holder Account when a new user registers.
    """
    print(f"post_save signal triggered for user: {instance.email}, created: {created}")
    if not created:
        return

    try:    
        Account.objects.get_or_create(
            user=instance,
            account_type="holder",
            is_active=True,
            defaults={"balance": 0},
        )
    except Exception as e:
        print(f"Error creating holder account for user {instance.email}: {e}")
    try:
        fleet_group = Group.objects.get(name="Flota")
        instance.groups.add(fleet_group)
    except Group.DoesNotExist:
        pass


@receiver(post_save, sender=Dependents)
def post_save_dependent(sender, instance, created, **kwargs):
    """
    Check if the user should lose the 'Flota' role when a Dependent relationship is ended.
    """
    # We only care if the relationship has ended (has an end_date)
    # If it's a new record (created=True) it likely doesn't have an end_date yet (or shouldn't), 
    # but we check if end_date is present just in case.
    
    if not instance.end_date:
        # Relationship is active, so they definitely keep/get logic (handled elsewhere or implied)
        return

    # If we are here, end_date IS set.
    
    dependent_account = instance.dependent_account
    user = dependent_account.user
    
    if not user:
        return

    # Check 1: Does the user have an active Titular Account?
    # We assume 'is_active' determines if the account is usable.
    has_titular = Account.objects.filter(
        user=user, 
        account_type='holder', 
        is_active=True
    ).exists()
    
    if has_titular:
        return

    # Check 2: Is the user part of ANY OTHER fleet as an active dependent?
    # We look for any 'Dependents' relationship where:
    # - dependent_account belongs to THIS user
    # - end_date is None (active relationship)
    # 
    # Note: user might have multiple 'dependent' accounts (one per fleet invitation? 
    # Wait, the user said "a user can have multiple accounts of type dependent").
    # So we must verify across ALL their dependent accounts.
    
    active_fleet_memberships = Dependents.objects.filter(
        dependent_account__user=user,
        end_date__isnull=True
    ).exists()
    
    if active_fleet_memberships:
        return

    # If no titular account and no other active fleet memberships, remove the role.
    try:
        fleet_group = Group.objects.get(name='Flota')
        user.groups.remove(fleet_group)
    except Group.DoesNotExist:
        pass
