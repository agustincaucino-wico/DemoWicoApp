from accounts.models import Account
from django.db import transaction

from django.contrib.auth.models import Group

class PromotionActions:
    @staticmethod
    def create_holder_account(user, params=None):
        """
        Creates a holder account for the user if one does not exist.
        """
        # Check if holder account already exists
        if Account.objects.filter(user=user, account_type="holder").exists():
            return {
                "success": False,
                "message": "Ya tienes una cuenta de WICORED."
            }

        try:
            # We assume the signal or manager usually creates it, but if manual creation is forced:
            # Note: The Account model has a unique constraint, so duplicate creation would fail anyway.
            # But we want to handle it gracefully.
            
            # Since auto-creation might be in place elsewhere, we just ensure it exists or create it.
            # Given the requirement: "por ahora la cuenta titular se crea automaticamente pero esto en un futuro se va a cambiar"
            # It implies we should forcefully create it if not present, which matches logic.
            
            Account.objects.create(
                user=user,
                balance=0,
                account_type="holder"
            )
            
            # Check for 'assign_fleet_role' param
            if params and params.get('assign_fleet_role'):
                try:
                    fleet_group = Group.objects.get(name='Flota')
                    user.groups.add(fleet_group)
                except Group.DoesNotExist:
                    pass # Or handle error appropriately

            return {
                "success": True,
                "message": "Cuenta titular creada exitosamente."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error al crear cuenta titular: {str(e)}"
            }

    @classmethod
    def execute(cls, action_type, user, params=None):
        if action_type == 'CREATE_HOLDER_ACCOUNT':
            return cls.create_holder_account(user, params)
        return {
            "success": False,
            "message": "Acción no reconocida."
        }
