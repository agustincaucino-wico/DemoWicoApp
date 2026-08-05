from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from users.models import CustomUser
from users.roles import ROLES
from django.contrib.auth.models import Group, Permission
from accounts.models import Account
from operation.models import ModifyFunds
from .models import PromotionCode, PromotionRedemption
from django.utils import timezone
from datetime import timedelta

class PromotionTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="testuser@example.com", 
            password="pass1234"
        )
        # Note: Account might be auto-created by signals depending on existing code, 
        # but the requirement implies it might not be, or we want to test creation.
        # However, `accounts` tests showed `test_holder_account_auto_created`.
        # If it IS auto-created, we might need to delete it to test the "creation" action, 
        # or test that the action handles existing accounts gracefully.
        
        # Checking if account exists
        self.account_exists = Account.objects.filter(user=self.user, account_type="holder").exists()
        
        # Create client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create Promotion Code
        self.promo_code, created = PromotionCode.objects.get_or_create(
            code="WICORED",
            defaults={
                'action_type': "CREATE_HOLDER_ACCOUNT",
                'active': True
            }
        )
        if not created:
            self.promo_code.action_type = "CREATE_HOLDER_ACCOUNT"
            self.promo_code.active = True
            self.promo_code.save()

    def test_redeem_create_holder_account(self):
        # If account auto-exists, let's delete it to test creation if possible, 
        # BUT if the system enforces it, maybe we can't easily. 
        # Let's see what happens.
        if self.account_exists:
            # If it exists, let's just make sure the redundancy check works
            response = self.client.post('/promotions/redeem/', {"code": "WICORED"})
            # Expecting 400 with "already exists" message as per requirements
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("Ya tienes una cuenta de WICORED.", response.data['error'])
        else:
            response = self.client.post('/promotions/redeem/', {"code": "WICORED"})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(Account.objects.filter(user=self.user, account_type="holder").exists())
            
    def test_redeem_invalid_code(self):
        response = self.client.post('/promotions/redeem/', {"code": "INVALID"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "El código ingresado no existe.")

    def test_redeem_expired_code(self):
        expired_code = PromotionCode.objects.create(
            code="EXPIRED",
            action_type="CREATE_HOLDER_ACCOUNT",
            valid_to=timezone.now() - timedelta(days=1)
        )
        response = self.client.post('/promotions/redeem/', {"code": "EXPIRED"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "El código ha expirado o no es válido.")

    def test_double_redemption(self):
        # Create a code that doesn't conflict with account creation to test double redemption logic cleanly?
        # Or just use the WICORED one.
        
        # If account exists, the first redeem will fail on "Account exists" logic BEFORE "Double redemption" check?
        # Wait, my view checks `PromotionRedemption` BEFORE executing action.
        # So if I redeem once, insert Redemption record?
        # NO, if action fails, I do NOT insert Redemption record in my view logic (I check `if not result.get('success'): return`).
        
        # So if account exists, I can never "successfully" redeem this specific code type?
        # That logic seems fine for this specific action.
        
        # To test double redemption, I need a successful first redemption.
        # Let's try to delete the account to allow success.
        if self.account_exists:
            Account.objects.filter(user=self.user).delete()
            
        # First redemption
        response = self.client.post('/promotions/redeem/', {"code": "WICORED"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Second redemption
        response = self.client.post('/promotions/redeem/', {"code": "WICORED"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "Ya canjeaste este código.")

    def test_redeem_gift_balance_creates_modify_funds_record(self):
        gift_code = PromotionCode.objects.create(
            code="GIFT100",
            action_type="GIFT_BALANCE",
            action_params={"amount": 100},
        )

        if self.account_exists:
            holder_account = Account.objects.get(user=self.user, account_type="holder")
        else:
            holder_account = Account.objects.create(
                user=self.user, balance=0, account_type="holder"
            )

        response = self.client.post('/promotions/redeem/', {"code": "GIFT100"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        holder_account.refresh_from_db()
        self.assertEqual(holder_account.balance, Decimal("100"))

        record = ModifyFunds.objects.filter(account=holder_account).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.account, holder_account)
        self.assertEqual(record.amount, Decimal("100"))
        self.assertEqual(record.gestor, self.user)
        self.assertIn("canje de código promocional", record.comments)
        self.assertIn("autoservicio", record.comments)

