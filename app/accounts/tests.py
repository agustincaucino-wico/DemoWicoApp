from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission, Group

from rest_framework.test import APIClient
from rest_framework import status

from users.models import CustomUser
from users.roles import ROLES
from .models import Account, Dependents, Plates, DependentInvitation


class AccountsTestCase(TestCase):
    def setUp(self):
        # Create two users, a holder and a dependent user
        self.user_holder = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self.user_dependent = CustomUser.objects.create_user(
            email="dependent@example.com", password="pass1234"
        )

        # Assign Gestor role (group + permissions) to users
        self._assign_gestor_role(self.user_holder)
        self._assign_gestor_role(self.user_dependent)

        # The user manager auto-creates a holder Account per user
        self.holder_account = Account.objects.get(
            user=self.user_holder, account_type="holder"
        )

        # Create a dependent account for the dependent user (not auto-created)
        self.dependent_account = Account.objects.create(
            user=self.user_dependent, balance=0, account_type="dependent"
        )

        # Create clients for API requests
        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.user_holder)

        self.dependent_client = APIClient()
        self.dependent_client.force_authenticate(user=self.user_dependent)

    def _assign_gestor_role(self, user):
        """Assign Gestor group and permissions to the user."""
        # Create or get the Gestor group
        gestor_group, _ = Group.objects.get_or_create(name="Gestor")

        # Assign permissions to the group
        gestor_permissions = ROLES.get("Gestor", [])
        permissions = Permission.objects.filter(codename__in=gestor_permissions)
        gestor_group.permissions.set(permissions)

        # Add user to the Gestor group
        user.groups.add(gestor_group)

    def test_holder_account_auto_created(self):
        # The CustomUser manager should create a holder account automatically
        account = Account.objects.get(user=self.user_holder, account_type="holder")
        self.assertIsNotNone(account)

    def test_unique_holder_constraint(self):
        # Trying to create another holder account for the same user should raise an error
        with self.assertRaises(IntegrityError):
            Account.objects.create(
                user=self.user_holder, balance=0, account_type="holder"
            )

    def test_update_balance_action(self):
        # Update balance via action endpoint
        url = f"/accounts/accounts/{self.holder_account.id}/update-balance/"
        response = self.holder_client.patch(url, {"balance": 100.50}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.holder_account.refresh_from_db()
        self.assertEqual(float(self.holder_account.balance), 100.5)

        # Negative balance should be rejected
        response = self.holder_client.patch(url, {"balance": -10}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plate_and_authorized_plate_creation_and_validation(self):
        # Create a plate owned by the holder
        plate_payload = {
            "plate_number": "ABC123",
            "holder_account": self.holder_account.id,
            "start_date": timezone.now().date().isoformat(),
        }
        response = self.holder_client.post(
            "/accounts/plates/", plate_payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plate_id = (
            response.data["id"]
            if isinstance(response.data, dict)
            else response.data.get("id")
        )
        plate_obj = (
            Plates.objects.get(id=response.data["id"])
            if isinstance(response.data, dict)
            else Plates.objects.get(id=plate_id)
        )

        # Authorize the plate for the dependent (should fail because no relationship exists yet)
        auth_payload = {
            "dependent_account": self.dependent_account.id,
            "plate": plate_obj.id,
            "start_date": timezone.now().date().isoformat(),
        }
        response = self.holder_client.post(
            "/accounts/authorized-plates/", auth_payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Create a dependents relation
        Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )

        # Now authorizing should succeed
        response = self.holder_client.post(
            "/accounts/authorized-plates/", auth_payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Ensure dependent user can see the authorized plate via the 'user plates' endpoint
        response = self.dependent_client.get("/actions/user/plates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plates = response.data
        self.assertTrue(
            any(
                p["plate_number"] == "ABC123" and p["ownership_type"] == "authorized"
                for p in plates
            )
        )

        # Test duplicate authorization - should fail with validation error
        response = self.holder_client.post(
            "/accounts/authorized-plates/", auth_payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Ya existe una autorización activa", str(response.data))

    def test_dependent_invitation_flow_models(self):
        # Create an invitation and accept it via model methods
        invitation = DependentInvitation.objects.create(
            holder_account=self.holder_account,
            dependent_email=self.user_dependent.email,
        )

        # Accept invitation (should create a dependent account for dependent user)
        invitation.accept_invitation()
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")

        # Now a Dependents relation should exist
        relation = Dependents.objects.filter(
            holder_account=self.holder_account,
            dependent_account__user__email=self.user_dependent.email,
            end_date__isnull=True,
        ).first()
        self.assertIsNotNone(relation)

        # Trying to accept again should raise a ValidationError
        with self.assertRaises(ValidationError):
            invitation.accept_invitation()

    def test_remove_dependent_via_api(self):
        # Create a dependent relation first
        Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )

        # Set initial balances
        self.holder_account.balance = 1000
        self.holder_account.save()
        self.dependent_account.balance = 250
        self.dependent_account.save()

        # Holder removes dependent via API
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_account_id": self.dependent_account.id,
        }
        response = self.holder_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify balance was transferred
        self.assertIn("balance_transferred", response.data)
        self.assertEqual(float(response.data["balance_transferred"]), 250.0)
        self.assertIn("new_holder_balance", response.data)
        self.assertEqual(float(response.data["new_holder_balance"]), 1250.0)

        # Refresh from DB and verify
        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(float(self.holder_account.balance), 1250.0)
        self.assertEqual(float(self.dependent_account.balance), 0.0)

        # Removing again should return 404 - relationship no longer active
        response = self.holder_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Dependent user cannot remove themselves because they don't own the holder account
        # The API returns 404 since the holder_account doesn't belong to the dependent user
        Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )
        response = self.dependent_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        # Dependent doesn't own holder_account, so it returns 404 (not found for this user)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_dependent_directly_via_api(self):
        # Create a new user to add as dependent
        new_dependent_user = CustomUser.objects.create_user(
            email="newdependent@example.com", password="pass1234"
        )

        # Holder adds dependent directly via new API endpoint
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": new_dependent_user.email,
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("dependent_account_id", response.data)
        self.assertIn("relationship_id", response.data)

        # Verify dependent account was created
        dependent_account = Account.objects.get(
            user=new_dependent_user, account_type="dependent"
        )
        self.assertIsNotNone(dependent_account)

        # Verify dependent relationship was created
        relationship = Dependents.objects.get(
            holder_account=self.holder_account,
            dependent_account=dependent_account,
            end_date__isnull=True,
        )
        self.assertIsNotNone(relationship)

        # Try to add the same user again - should fail
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_add_self_as_dependent(self):
        # Try to add self as dependent - should fail
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": self.user_holder.email,
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_dependent_with_nonexistent_email(self):
        """Test adding dependent with email that doesn't exist"""
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": "nonexistent@example.com",
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_dependent_with_invalid_holder_account(self):
        """Test adding dependent with holder account that doesn't belong to user"""
        # Create another holder user
        other_holder_user = CustomUser.objects.create_user(
            email="other-holder@example.com", password="pass1234"
        )
        other_holder_account = Account.objects.get(
            user=other_holder_user, account_type="holder"
        )

        # Try to use other user's holder account
        new_dependent_user = CustomUser.objects.create_user(
            email="newdep@example.com", password="pass1234"
        )
        payload = {
            "holder_account_id": other_holder_account.id,
            "dependent_email": new_dependent_user.email,
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_dependent_missing_fields(self):
        """Test adding dependent with missing required fields"""
        # Missing dependent_email
        payload = {"holder_account_id": self.holder_account.id}
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Missing holder_account_id
        payload = {"dependent_email": "test@example.com"}
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_dependent_with_zero_balance(self):
        """Test removing dependent with zero balance"""
        # Create dependent relationship
        Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )

        # Set balances
        self.holder_account.balance = 500
        self.holder_account.save()
        self.dependent_account.balance = 0
        self.dependent_account.save()

        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_account_id": self.dependent_account.id,
        }
        response = self.holder_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data["balance_transferred"]), 0.0)
        self.assertEqual(float(response.data["new_holder_balance"]), 500.0)
        self.assertEqual(float(self.holder_account.balance), 500.0)
        self.assertEqual(float(self.dependent_account.balance), 0.0)

    def test_remove_dependent_unauthorized_user(self):
        """Test that a user cannot remove dependents from an account they don't own"""
        # Create another holder user
        other_holder_user = CustomUser.objects.create_user(
            email="unauthorized@example.com", password="pass1234"
        )
        self._assign_gestor_role(other_holder_user)
        other_holder_account = Account.objects.get(
            user=other_holder_user, account_type="holder"
        )

        # Create dependent relationship
        Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )

        # Try to remove using unauthorized client
        unauthorized_client = APIClient()
        unauthorized_client.force_authenticate(user=other_holder_user)

        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_account_id": self.dependent_account.id,
        }
        response = unauthorized_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_nonexistent_dependent_relationship(self):
        """Test removing a dependent relationship that doesn't exist"""
        # Don't create any relationship
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_account_id": self.dependent_account.id,
        }
        response = self.holder_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_dependent_creates_dependent_account_if_not_exists(self):
        """Test that adding a dependent creates a dependent account if user doesn't have one"""
        # Create a new user without dependent account (only holder account exists)
        new_user = CustomUser.objects.create_user(
            email="newuser@example.com", password="pass1234"
        )

        # Verify only holder account exists
        self.assertTrue(
            Account.objects.filter(user=new_user, account_type="holder").exists()
        )
        self.assertFalse(
            Account.objects.filter(user=new_user, account_type="dependent").exists()
        )

        # Add as dependent
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": new_user.email,
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify dependent account was created
        self.assertTrue(
            Account.objects.filter(user=new_user, account_type="dependent").exists()
        )
        dependent_account = Account.objects.get(user=new_user, account_type="dependent")
        self.assertEqual(float(dependent_account.balance), 0.0)

    def test_add_multiple_dependents_to_same_holder(self):
        """Test adding multiple different dependents to the same holder"""
        # Create two new users
        dep1 = CustomUser.objects.create_user(
            email="dep1@example.com", password="pass1234"
        )
        dep2 = CustomUser.objects.create_user(
            email="dep2@example.com", password="pass1234"
        )

        # Add first dependent
        payload1 = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": dep1.email,
        }
        response1 = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload1, format="json"
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Add second dependent
        payload2 = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": dep2.email,
        }
        response2 = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload2, format="json"
        )
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        # Verify both relationships exist
        dep1_account = Account.objects.get(user=dep1, account_type="dependent")
        dep2_account = Account.objects.get(user=dep2, account_type="dependent")

        self.assertTrue(
            Dependents.objects.filter(
                holder_account=self.holder_account,
                dependent_account=dep1_account,
                end_date__isnull=True,
            ).exists()
        )
        self.assertTrue(
            Dependents.objects.filter(
                holder_account=self.holder_account,
                dependent_account=dep2_account,
                end_date__isnull=True,
            ).exists()
        )

    def test_remove_dependent_with_large_balance(self):
        """Test removing dependent with a large balance to verify transfer"""
        # Create dependent relationship
        Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )

        # Set large balances
        self.holder_account.balance = 10000.50
        self.holder_account.save()
        self.dependent_account.balance = 5000.75
        self.dependent_account.save()

        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_account_id": self.dependent_account.id,
        }
        response = self.holder_client.post(
            "/actions/remove-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data["balance_transferred"]), 5000.75)
        self.assertEqual(float(response.data["new_holder_balance"]), 15001.25)

        # Verify in database
        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(float(self.holder_account.balance), 15001.25)
        self.assertEqual(float(self.dependent_account.balance), 0.0)
