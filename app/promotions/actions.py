from accounts.models import Account
from django.db import transaction

from django.contrib.auth.models import Group
from decimal import Decimal


class PromotionActions:
    @staticmethod
    def create_holder_account(user, params=None):
        """
        Creates a holder account for the user if one does not exist and assigns the 'Flota' group.
        """
        # Check if holder account already exists
        if Account.objects.filter(user=user, account_type="holder").exists():
            return {"success": False, "message": "Ya tienes una cuenta de WICORED."}

        try:
            # We assume the signal or manager usually creates it, but if manual creation is forced:
            # Note: The Account model has a unique constraint, so duplicate creation would fail anyway.
            # But we want to handle it gracefully.

            # Since auto-creation might be in place elsewhere, we just ensure it exists or create it.
            # Given the requirement: "por ahora la cuenta titular se crea automaticamente pero esto en un futuro se va a cambiar"
            # It implies we should forcefully create it if not present, which matches logic.

            Account.objects.create(user=user, balance=0, account_type="holder")

            try:
                fleet_group = Group.objects.get(name="Flota")
                user.groups.add(fleet_group)
            except Group.DoesNotExist:
                pass

            return {"success": True, "message": "Cuenta titular creada exitosamente."}
        except Exception as e:
            return {
                "success": False,
                "message": f"Error al crear cuenta titular: {str(e)}",
            }

    @staticmethod
    def gift_balance(user, params=None):
        """
        Adds balance to the user's holder account.
        Expected params: {'amount': number (will be converted to Decimal)}
        """
        if not params or "amount" not in params:
            return {
                "success": False,
                "message": "El código no tiene configurado el monto a regalar.",
            }

        try:
            amount = Decimal(str(params["amount"]))
            if amount <= 0:
                return {
                    "success": False,
                    "message": "El monto a regalar debe ser mayor a cero.",
                }
        except (ValueError, TypeError):
            return {"success": False, "message": "El monto configurado no es válido."}

        try:
            # Get or create holder account
            holder_account = Account.objects.filter(
                user=user, account_type="holder"
            ).first()

            if not holder_account:
                return {
                    "success": False,
                    "message": "No tienes una cuenta titular. Primero debes solicitar una cuenta de WICORED.",
                }

            # Add balance
            holder_account.balance += amount
            holder_account.save()

            return {
                "success": True,
                "message": f"Se han acreditado ${amount:.2f} a tu cuenta.",
                "amount": float(amount),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error al acreditar el saldo: {str(e)}",
            }

    @classmethod
    def execute(cls, action_type, user, params=None):
        if action_type == "CREATE_HOLDER_ACCOUNT":
            return cls.create_holder_account(user, params)
        elif action_type == "GIFT_BALANCE":
            return cls.gift_balance(user, params)
        return {"success": False, "message": "Acción no reconocida."}
