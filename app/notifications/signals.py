"""
Signals for automatic notification creation based on system events.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from notifications.models import Notification, NotificationPreference

User = get_user_model()


# @receiver(post_save, sender=User)
# def create_notification_preferences(sender, instance, created, **kwargs):
#     """
#     Create default notification preferences when a new user is created.
#     """
#     if created:
#         NotificationPreference.objects.get_or_create(
#             user=instance,
#             defaults={
#                 "push_enabled": True,
#                 "email_enabled": True,
#                 "fuel_load_notifications": True,
#                 "balance_notifications": True,
#                 "account_notifications": True,
#                 "system_notifications": True,
#             },
#         )


# @receiver(post_save, sender="actions.FuelLoad")
def notify_fuel_load_completed(sender, instance, created, **kwargs):
    """Create notification when a fuel load is completed"""
    # Only create notification when timestamp_finished is set (operation completed)
    if not created and instance.timestamp_finished is not None:
        # Check if we already notified about this fuel load to avoid duplicates
        existing_notification = Notification.objects.filter(
            user=instance.user,
            notification_type="fuel",
        ).exists()

        if not existing_notification:
            Notification.create_notification(
                user=instance.user,
                title="Carga de combustible exitosa",
                message=f"Se cargo ${instance.final_amount} en {instance.station.name}",
                notification_type="fuel",
            )


# @receiver(post_save, sender='accounts.Account')
# def notify_low_balance(sender, instance, created, **kwargs):
#     """Create notification when account balance is low"""
#     if not created:
#         threshold = 10000  # Define your threshold
#         if float(instance.balance) < threshold:
#             # Check if notification was already sent recently
#             # to avoid spam
#             Notification.create_notification(
#                 user=instance.user,
#                 title="Saldo bajo",
#                 message=f"Tu cuenta {instance.account_type} tiene un saldo de ${instance.balance}. Considera recargar pronto.",
#                 notification_type='warning',
#                 action_url=f'/(app)/wicored/balance?accountId={instance.id}'
#             )


# @receiver(post_save, sender='accounts.Dependents')
# def notify_dependent_added(sender, instance, created, **kwargs):
#     """Create notification when a dependent is added to an account"""
#     if created:
#         Notification.create_notification(
#             user=instance.holder_account.user,
#             title="Adherente agregado",
#             message=f"{instance.dependent_user.get_full_name()} fue agregado como adherente a tu cuenta",
#             notification_type='account',
#         )


# Add more signal handlers as needed for different events
