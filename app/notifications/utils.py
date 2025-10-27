"""
Utility functions for creating notifications in the system.
"""

from notifications.models import Notification


# def create_fuel_load_notification(
#     user, station_name, liters, fuel_type, action_url=None
# ):
#     """
#     Create a notification for a successful fuel load.

#     Args:
#         user: CustomUser instance
#         station_name: Name of the station
#         liters: Amount of liters loaded
#         fuel_type: Type of fuel
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title="Carga de combustible exitosa",
#         message=f"Se cargaron {liters} litros de {fuel_type} en {station_name}",
#         notification_type="fuel",
#         action_url=action_url,
#     )


# def create_low_balance_notification(user, account_type, balance, action_url=None):
#     """
#     Create a notification for low account balance.

#     Args:
#         user: CustomUser instance
#         account_type: Type of account (holder/dependent)
#         balance: Current balance
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title="Saldo bajo",
#         message=f"Tu cuenta {account_type} tiene un saldo de ${balance:,.0f}. Considera recargar pronto.",
#         notification_type="warning",
#         action_url=action_url,
#     )


# def create_balance_credited_notification(user, amount, account_type, action_url=None):
#     """
#     Create a notification for successful balance credit.

#     Args:
#         user: CustomUser instance
#         amount: Amount credited
#         account_type: Type of account
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title="Recarga exitosa",
#         message=f"Se acreditaron ${amount:,.0f} en tu cuenta {account_type}",
#         notification_type="success",
#         action_url=action_url,
#     )


# def create_dependent_added_notification(user, dependent_name, action_url=None):
#     """
#     Create a notification when a dependent is added to an account.

#     Args:
#         user: CustomUser instance (holder)
#         dependent_name: Full name of the dependent
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title="Adherente agregado",
#         message=f"{dependent_name} fue agregado como adherente a tu cuenta",
#         notification_type="account",
#         action_url=action_url,
#     )


# def create_new_station_notification(
#     user, station_name, station_address, action_url=None
# ):
#     """
#     Create a notification for a new station available.

#     Args:
#         user: CustomUser instance
#         station_name: Name of the station
#         station_address: Address of the station
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title="Nueva estación disponible",
#         message=f"Ya podés cargar combustible en {station_name} - {station_address}",
#         notification_type="info",
#         action_url=action_url,
#     )


# def create_system_notification(user, title, message, action_url=None):
#     """
#     Create a generic system notification.

#     Args:
#         user: CustomUser instance
#         title: Notification title
#         message: Notification message
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title=title,
#         message=message,
#         notification_type="info",
#         action_url=action_url,
#     )


# def create_error_notification(user, title, message, action_url=None):
#     """
#     Create an error notification.

#     Args:
#         user: CustomUser instance
#         title: Notification title
#         message: Notification message
#         action_url: Optional URL to navigate to
#     """
#     return Notification.create_notification(
#         user=user,
#         title=title,
#         message=message,
#         notification_type="error",
#         action_url=action_url,
#     )


# def notify_all_users(
#     title, message, notification_type="info", action_url=None, user_filter=None
# ):
#     """
#     Send a notification to all users or a filtered set of users.

#     Args:
#         title: Notification title
#         message: Notification message
#         notification_type: Type of notification
#         action_url: Optional URL to navigate to
#         user_filter: Optional Q object to filter users

#     Returns:
#         Number of notifications created
#     """
#     from users.models import CustomUser

#     users = CustomUser.objects.filter(is_active=True)
#     if user_filter:
#         users = users.filter(user_filter)

#     notifications = [
#         Notification(
#             user=user,
#             title=title,
#             message=message,
#             type=notification_type,
#             action_url=action_url,
#         )
#         for user in users
#     ]

#     Notification.objects.bulk_create(notifications)
#     return len(notifications)
