from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission, Group
from django.urls import reverse

from rest_framework.test import APIClient
from rest_framework import status

from model_bakery import baker

from users.models import CustomUser
from users.roles import ROLES
from users.test_helpers import RoleAssignmentMixin
from .models import (
    Account,
    Dependents,
    Plates,
    DependentInvitation,
    Organism,
    AuthorizedEmail,
)


class AccountsTestCase(RoleAssignmentMixin, TestCase):
    def setUp(self):
        # Create two users, a holder and a dependent user
        self.user_holder = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self.user_dependent = CustomUser.objects.create_user(
            email="dependent@example.com", password="pass1234"
        )

        # Assign Gestor role (group + permissions) to users
        self.assign_role(self.user_holder, "Gestor")
        self.assign_role(self.user_dependent, "Gestor")

        # Get the auto-created holder account (created by post_save signal)
        self.holder_account = Account.objects.get(
            user=self.user_holder, account_type="holder"
        )

        # Create a dependent account for the dependent user (not auto-created)
        self.dependent_account = baker.make(
            Account, user=self.user_dependent, account_type="dependent"
        )

        # Create clients for API requests
        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.user_holder)

        self.dependent_client = APIClient()
        self.dependent_client.force_authenticate(user=self.user_dependent)

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

    def test_balance_max_limit_15_digits(self):
        """Test that balance can support up to 15 digits (13 integer + 2 decimal)"""
        url = f"/accounts/accounts/{self.holder_account.id}/update-balance/"

        # Test maximum valid balance: 9,999,999,999,999.99
        max_balance = "9999999999999.99"
        response = self.holder_client.patch(
            url, {"balance": max_balance}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.holder_account.refresh_from_db()
        self.assertEqual(str(self.holder_account.balance), max_balance)

        # Test large valid balance with 13 integer digits
        large_balance = "1234567890123.45"
        response = self.holder_client.patch(
            url, {"balance": large_balance}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.holder_account.refresh_from_db()
        self.assertEqual(str(self.holder_account.balance), large_balance)

    def test_balance_exceeds_max_limit(self):
        """Test that balance exceeding 15 digits is rejected"""
        url = f"/accounts/accounts/{self.holder_account.id}/update-balance/"

        # Test balance exceeding maximum: 10,000,000,000,000.00
        over_max_balance = "10000000000000.00"
        response = self.holder_client.patch(
            url, {"balance": over_max_balance}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("balance", str(response.data).lower())

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
        baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
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
        baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
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
        baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
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
        """Test adding dependent with email that doesn't exist creates a pending invitation"""
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": "nonexistent@example.com",
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data.get("user_registered", True))
        self.assertTrue(
            AuthorizedEmail.objects.filter(
                email="nonexistent@example.com",
                dependent_of=self.holder_account,
                status="pending",
            ).exists()
        )

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
        baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
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
        self.assign_role(other_holder_user, "Gestor")
        other_holder_account = Account.objects.get(
            user=other_holder_user, account_type="holder"
        )

        # Create dependent relationship
        baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
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
        # Create a new user without any account
        new_user = CustomUser.objects.create_user(
            email="newuser@example.com", password="pass1234"
        )

        # Holder account is auto-created by signal; verify no dependent account yet
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
        baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
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


class PlatesSoftDeleteTestCase(TestCase):
    """Test soft delete functionality for Plates"""

    def setUp(self):
        # Create user and holder account
        self.user_holder = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self._assign_gestor_role(self.user_holder)

        self.holder_account = Account.objects.get(
            user=self.user_holder, account_type="holder"
        )

        # Create API client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user_holder)

    def _assign_gestor_role(self, user):
        """Assign Gestor group and permissions to the user."""
        gestor_group, _ = Group.objects.get_or_create(name="Gestor")

        # Get all permissions for the accounts app
        permissions = Permission.objects.filter(
            content_type__app_label__in=["accounts", "actions"]
        )
        gestor_group.permissions.set(permissions)
        user.groups.add(gestor_group)

    def test_delete_plate_sets_end_date(self):
        """Test that deleting a plate sets end_date instead of removing it"""
        # Create a plate
        plate = Plates.objects.create(
            plate_number="ABC123",
            holder_account=self.holder_account,
            start_date=timezone.now().date(),
        )

        # Delete the plate via API
        response = self.client.delete(f"/accounts/plates/{plate.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertIn("end_date", response.data)

        # Verify plate still exists but has end_date
        plate.refresh_from_db()
        self.assertIsNotNone(plate.end_date)
        self.assertEqual(plate.end_date, timezone.now().date())

    def test_cannot_delete_already_deleted_plate(self):
        """Test that deleting an already deleted plate returns error"""
        # Create a plate with end_date
        plate = Plates.objects.create(
            plate_number="ABC123",
            holder_account=self.holder_account,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
        )

        # Try to delete again
        response = self.client.delete(f"/accounts/plates/{plate.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_cannot_create_duplicate_active_plate(self):
        """Test that creating a plate with same number as active plate fails"""
        # Create first plate
        Plates.objects.create(
            plate_number="ABC123",
            holder_account=self.holder_account,
            start_date=timezone.now().date(),
        )

        # Try to create duplicate
        payload = {
            "plate_number": "ABC123",
            "holder_account": self.holder_account.id,
            "start_date": timezone.now().date().isoformat(),
        }
        response = self.client.post("/accounts/plates/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_can_create_plate_after_soft_delete(self):
        """Test that a plate can be created after soft deleting the previous one"""
        # Create and soft delete a plate
        plate = Plates.objects.create(
            plate_number="ABC123",
            holder_account=self.holder_account,
            start_date=timezone.now().date(),
        )
        plate.end_date = timezone.now().date()
        plate.save()

        # Create new plate with same number (should work)
        payload = {
            "plate_number": "ABC123",
            "holder_account": self.holder_account.id,
            "start_date": timezone.now().date().isoformat(),
        }
        response = self.client.post("/accounts/plates/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class RoleBasedAccessControlTestCase(RoleAssignmentMixin, TestCase):
    """Test that Gestor can access all resources while Flota users can only access their own"""

    def setUp(self):
        # Create two Flota users
        self.flota_user1 = CustomUser.objects.create_user(
            email="flota1@example.com", password="pass1234"
        )
        self.flota_user2 = CustomUser.objects.create_user(
            email="flota2@example.com", password="pass1234"
        )

        # Create one Gestor user
        self.gestor_user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )

        # Assign roles
        self._assign_flota_role(self.flota_user1)
        self._assign_flota_role(self.flota_user2)
        self.assign_role(self.gestor_user, "Gestor")

        # Get auto-created holder accounts and set balances
        self.flota1_account = Account.objects.get(
            user=self.flota_user1, account_type="holder"
        )
        self.flota1_account.balance = 1000
        self.flota1_account.save(update_fields=["balance"])
        self.flota2_account = Account.objects.get(
            user=self.flota_user2, account_type="holder"
        )
        self.flota2_account.balance = 2000
        self.flota2_account.save(update_fields=["balance"])

        # Create plates for both flota users
        self.flota1_plate = baker.make(
            Plates, plate_number="FLO001", holder_account=self.flota1_account
        )
        self.flota2_plate = baker.make(
            Plates, plate_number="FLO002", holder_account=self.flota2_account
        )

        # Create dependent accounts
        self.flota1_dependent = baker.make(
            Account, user=self.flota_user1, account_type="dependent"
        )
        self.flota2_dependent = baker.make(
            Account, user=self.flota_user2, account_type="dependent"
        )

        # Create dependent relationships
        self.flota1_dep_relation = baker.make(
            Dependents,
            holder_account=self.flota1_account,
            dependent_account=self.flota1_dependent,
        )
        self.flota2_dep_relation = baker.make(
            Dependents,
            holder_account=self.flota2_account,
            dependent_account=self.flota2_dependent,
        )

        # Create API clients
        self.flota1_client = APIClient()
        self.flota1_client.force_authenticate(user=self.flota_user1)

        self.flota2_client = APIClient()
        self.flota2_client.force_authenticate(user=self.flota_user2)

        self.gestor_client = APIClient()
        self.gestor_client.force_authenticate(user=self.gestor_user)

    def _assign_flota_role(self, user):
        """Assign Flota group and permissions to the user."""
        flota_group, _ = Group.objects.get_or_create(name="Flota")

        # Assign necessary permissions for Flota users
        flota_permissions = ROLES.get("Flota", [])
        if flota_permissions:
            permissions = Permission.objects.filter(codename__in=flota_permissions)
            flota_group.permissions.set(permissions)
        else:
            # If Flota role is not defined in ROLES, assign basic view permissions
            permissions = Permission.objects.filter(
                codename__in=[
                    "view_account",
                    "view_plates",
                    "view_dependents",
                    "view_authorizedplates",
                ]
            )
            flota_group.permissions.set(permissions)

        user.groups.add(flota_group)

    def test_flota_user_can_only_see_own_accounts(self):
        """Flota users should only see their own accounts"""
        response = self.flota1_client.get("/accounts/accounts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Flota1 should only see their own accounts
        account_ids = [acc["id"] for acc in response.data]
        self.assertIn(self.flota1_account.id, account_ids)
        self.assertIn(self.flota1_dependent.id, account_ids)
        self.assertNotIn(self.flota2_account.id, account_ids)
        self.assertNotIn(self.flota2_dependent.id, account_ids)

    def test_flota_user_can_only_see_own_plates(self):
        """Flota users should only see their own plates"""
        response = self.flota1_client.get("/accounts/plates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Flota1 should only see their own plates
        plate_ids = [plate["id"] for plate in response.data]
        self.assertIn(self.flota1_plate.id, plate_ids)
        self.assertNotIn(self.flota2_plate.id, plate_ids)

    def test_flota_user_can_only_see_own_dependents(self):
        """Flota users should only see their own dependent relationships"""
        response = self.flota1_client.get("/accounts/dependents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Flota1 should only see their own dependent relationships
        dep_ids = [dep["id"] for dep in response.data]
        self.assertIn(self.flota1_dep_relation.id, dep_ids)
        self.assertNotIn(self.flota2_dep_relation.id, dep_ids)

    def test_flota_user_cannot_access_other_users_account(self):
        """Flota users should not be able to access other users' accounts"""
        # Try to access flota2's account
        response = self.flota1_client.get(
            f"/accounts/accounts/{self.flota2_account.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_flota_user_cannot_access_other_users_plate(self):
        """Flota users should not be able to access other users' plates"""
        # Try to access flota2's plate
        response = self.flota1_client.get(f"/accounts/plates/{self.flota2_plate.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_flota_user_cannot_modify_other_users_plate(self):
        """Flota users should not be able to modify other users' plates"""
        # Try to update flota2's plate
        payload = {"brand": "Modified", "model": "Hacked"}
        response = self.flota1_client.patch(
            f"/accounts/plates/{self.flota2_plate.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_flota_user_cannot_delete_other_users_plate(self):
        """Flota users should not be able to delete other users' plates"""
        # Try to delete flota2's plate
        response = self.flota1_client.delete(
            f"/accounts/plates/{self.flota2_plate.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gestor_can_see_all_accounts(self):
        """Gestor users should see all accounts"""
        response = self.gestor_client.get("/accounts/accounts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Gestor should see both flota users' accounts
        account_ids = [acc["id"] for acc in response.data]
        self.assertIn(self.flota1_account.id, account_ids)
        self.assertIn(self.flota2_account.id, account_ids)
        self.assertIn(self.flota1_dependent.id, account_ids)
        self.assertIn(self.flota2_dependent.id, account_ids)

    def test_gestor_can_see_all_plates(self):
        """Gestor users should see all plates"""
        response = self.gestor_client.get("/accounts/plates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Gestor should see both flota users' plates
        plate_ids = [plate["id"] for plate in response.data]
        self.assertIn(self.flota1_plate.id, plate_ids)
        self.assertIn(self.flota2_plate.id, plate_ids)

    def test_gestor_can_see_all_dependents(self):
        """Gestor users should see all dependent relationships"""
        response = self.gestor_client.get("/accounts/dependents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Gestor should see both flota users' dependents
        dep_ids = [dep["id"] for dep in response.data]
        self.assertIn(self.flota1_dep_relation.id, dep_ids)
        self.assertIn(self.flota2_dep_relation.id, dep_ids)

    def test_gestor_can_access_any_account(self):
        """Gestor users should be able to access any account"""
        # Access flota1's account
        response = self.gestor_client.get(
            f"/accounts/accounts/{self.flota1_account.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Access flota2's account
        response = self.gestor_client.get(
            f"/accounts/accounts/{self.flota2_account.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gestor_can_modify_any_plate(self):
        """Gestor users should be able to modify any plate"""
        # Modify flota1's plate
        payload = {"brand": "Modified by Gestor", "model": "Test"}
        response = self.gestor_client.patch(
            f"/accounts/plates/{self.flota1_plate.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify modification
        self.flota1_plate.refresh_from_db()
        self.assertEqual(self.flota1_plate.brand, "Modified by Gestor")

    def test_flota_user_can_create_own_plate(self):
        """Flota users should be able to create plates for their own accounts"""
        payload = {
            "plate_number": "FLO003",
            "holder_account": self.flota1_account.id,
            "start_date": timezone.now().date().isoformat(),
        }
        response = self.flota1_client.post("/accounts/plates/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_flota_user_cannot_create_plate_for_other_user(self):
        """Flota users should not be able to create plates for other users' accounts"""
        payload = {
            "plate_number": "FLO004",
            "holder_account": self.flota2_account.id,
            "start_date": timezone.now().date().isoformat(),
        }
        response = self.flota1_client.post("/accounts/plates/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_flota_user_can_modify_own_plate(self):
        """Flota users should be able to modify their own plates"""
        payload = {"brand": "Modified", "model": "Own"}
        response = self.flota1_client.patch(
            f"/accounts/plates/{self.flota1_plate.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify modification
        self.flota1_plate.refresh_from_db()
        self.assertEqual(self.flota1_plate.brand, "Modified")

    def test_flota_user_can_delete_own_plate(self):
        """Flota users should be able to delete their own plates"""
        response = self.flota1_client.delete(
            f"/accounts/plates/{self.flota1_plate.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify soft delete
        self.flota1_plate.refresh_from_db()
        self.assertIsNotNone(self.flota1_plate.end_date)


class GestorAndFlotaRoleTestCase(RoleAssignmentMixin, TestCase):
    """Test that users with both Gestor and Flota roles get Gestor permissions"""

    def setUp(self):
        # Create users
        self.gestor_flota_user = CustomUser.objects.create_user(
            email="gestor-flota@example.com", password="pass1234"
        )
        self.flota_only_user = CustomUser.objects.create_user(
            email="flota-only@example.com", password="pass1234"
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@example.com", password="pass1234"
        )

        # Assign both Gestor and Flota roles to first user
        self.assign_role(self.gestor_flota_user, "Gestor")
        self._assign_flota_role(self.gestor_flota_user)

        # Assign only Flota role to second user
        self._assign_flota_role(self.flota_only_user)

        # Assign Gestor role to other user
        self.assign_role(self.other_user, "Gestor")

        # Get auto-created holder accounts (created by post_save signal)
        self.gestor_flota_account = Account.objects.get(
            user=self.gestor_flota_user, account_type="holder"
        )
        self.flota_only_account = Account.objects.get(
            user=self.flota_only_user, account_type="holder"
        )
        self.other_account = Account.objects.get(
            user=self.other_user, account_type="holder"
        )

        # Create plates
        self.gestor_flota_plate = baker.make(
            Plates, plate_number="GF001", holder_account=self.gestor_flota_account
        )
        self.flota_only_plate = baker.make(
            Plates, plate_number="FO001", holder_account=self.flota_only_account
        )
        self.other_plate = baker.make(
            Plates, plate_number="OT001", holder_account=self.other_account
        )

        # Create API clients
        self.gestor_flota_client = APIClient()
        self.gestor_flota_client.force_authenticate(user=self.gestor_flota_user)

        self.flota_only_client = APIClient()
        self.flota_only_client.force_authenticate(user=self.flota_only_user)

    def _assign_flota_role(self, user):
        """Assign Flota group and permissions to the user."""
        flota_group, _ = Group.objects.get_or_create(name="Flota")
        # Assign basic permissions for Flota users to manage their own resources
        permissions = Permission.objects.filter(
            codename__in=[
                "view_account",
                "change_account",
                "view_plates",
                "add_plates",
                "change_plates",
                "delete_plates",
                "view_dependents",
                "view_authorizedplate",
            ]
        )
        flota_group.permissions.set(permissions)
        user.groups.add(flota_group)

    def test_gestor_flota_user_can_see_all_accounts(self):
        """User with both Gestor and Flota roles should see all accounts (Gestor permissions)"""
        response = self.gestor_flota_client.get("/accounts/accounts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see all 3 accounts (Gestor permission)
        account_ids = {account["id"] for account in response.data}
        self.assertIn(self.gestor_flota_account.id, account_ids)
        self.assertIn(self.flota_only_account.id, account_ids)
        self.assertIn(self.other_account.id, account_ids)

    def test_flota_only_user_sees_own_accounts(self):
        """User with only Flota role should see only their own accounts"""
        response = self.flota_only_client.get("/accounts/accounts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see only their own account
        account_ids = {account["id"] for account in response.data}
        self.assertIn(self.flota_only_account.id, account_ids)
        self.assertNotIn(self.gestor_flota_account.id, account_ids)
        self.assertNotIn(self.other_account.id, account_ids)

    def test_gestor_flota_user_can_see_all_plates(self):
        """User with both Gestor and Flota roles should see all plates (Gestor permissions)"""
        response = self.gestor_flota_client.get("/accounts/plates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see all 3 plates (Gestor permission)
        plate_ids = {plate["id"] for plate in response.data}
        self.assertIn(self.gestor_flota_plate.id, plate_ids)
        self.assertIn(self.flota_only_plate.id, plate_ids)
        self.assertIn(self.other_plate.id, plate_ids)

    def test_flota_only_user_sees_own_plates(self):
        """User with only Flota role should see only their own plates"""
        response = self.flota_only_client.get("/accounts/plates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should see only their own plate
        plate_ids = {plate["id"] for plate in response.data}
        self.assertIn(self.flota_only_plate.id, plate_ids)
        self.assertNotIn(self.gestor_flota_plate.id, plate_ids)
        self.assertNotIn(self.other_plate.id, plate_ids)

    def test_gestor_flota_user_can_modify_any_plate(self):
        """User with both Gestor and Flota roles should be able to modify any plate"""
        # Try to modify another user's plate
        response = self.gestor_flota_client.patch(
            f"/accounts/plates/{self.flota_only_plate.id}/",
            {"brand": "Modified by Gestor-Flota"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify modification
        self.flota_only_plate.refresh_from_db()
        self.assertEqual(self.flota_only_plate.brand, "Modified by Gestor-Flota")

    def test_flota_only_user_cannot_modify_other_plate(self):
        """User with only Flota role should not be able to modify other users' plates"""
        # Try to modify another user's plate
        response = self.flota_only_client.patch(
            f"/accounts/plates/{self.gestor_flota_plate.id}/",
            {"brand": "Attempted modification"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Organism tests
# ---------------------------------------------------------------------------


class OrganismModelTests(TestCase):
    def test_create_organism(self):
        org = Organism.objects.create(
            name="Organismo genérico",
            cuit="30-12345678-9",
            billing_type="invoice",
        )
        self.assertEqual(str(org), "Organismo genérico")
        self.assertEqual(org.billing_type, "invoice")

    def test_organism_unique_name(self):
        Organism.objects.create(
            name="Organismo A", cuit="30-11111111-1", billing_type="invoice"
        )
        with self.assertRaises(Exception):
            Organism.objects.create(
                name="Organismo A", cuit="30-22222222-2", billing_type="prepaid"
            )

    def test_organism_unique_cuit(self):
        Organism.objects.create(
            name="Organismo A", cuit="30-11111111-1", billing_type="invoice"
        )
        with self.assertRaises(Exception):
            Organism.objects.create(
                name="Organismo B", cuit="30-11111111-1", billing_type="prepaid"
            )

    def test_organism_billing_types(self):
        org_invoice = Organism.objects.create(
            name="Facturación", cuit="30-11111111-1", billing_type="invoice"
        )
        org_prepaid = Organism.objects.create(
            name="Prepago", cuit="30-22222222-2", billing_type="prepaid"
        )
        self.assertEqual(org_invoice.billing_type, "invoice")
        self.assertEqual(org_prepaid.billing_type, "prepaid")


class OrganismAPITests(RoleAssignmentMixin, TestCase):
    def setUp(self):
        self.gestor_user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self.assign_role(self.gestor_user, "Gestor")
        self.gestor_client = APIClient()
        self.gestor_client.force_authenticate(user=self.gestor_user)

        self.regular_user = CustomUser.objects.create_user(
            email="regular@example.com", password="pass1234"
        )
        self.regular_client = APIClient()
        self.regular_client.force_authenticate(user=self.regular_user)

        self.flota_user = CustomUser.objects.create_user(
            email="flota@example.com", password="pass1234"
        )
        self.assign_role(self.flota_user, "Flota")
        self.flota_client = APIClient()
        self.flota_client.force_authenticate(user=self.flota_user)

        self.list_url = reverse("organism-list")

    def test_gestor_can_list_organisms(self):
        baker.make(Organism)
        response = self.gestor_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), Organism.objects.count())

    def test_gestor_can_create_organism(self):
        response = self.gestor_client.post(
            self.list_url,
            {
                "name": "Organismo de Prueba",
                "cuit": "30-99999999-9",
                "billing_type": "invoice",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Organism.objects.filter(name="Organismo de Prueba").exists())

    def test_gestor_can_update_organism(self):
        org = baker.make(Organism)
        url = reverse("organism-detail", args=[org.id])
        response = self.gestor_client.patch(
            url, {"billing_type": "prepaid"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        org.refresh_from_db()
        self.assertEqual(org.billing_type, "prepaid")

    def test_gestor_can_delete_organism(self):
        org = baker.make(Organism)
        url = reverse("organism-detail", args=[org.id])
        response = self.gestor_client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Organism.objects.filter(id=org.id).exists())

    def test_regular_user_cannot_list(self):
        response = self.regular_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_create(self):
        response = self.regular_client.post(
            self.list_url,
            {"name": "Hack", "cuit": "30-99999999-9", "billing_type": "invoice"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_flota_user_cannot_list(self):
        """Flota users have no organism permissions."""
        response = self.flota_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_flota_user_cannot_create(self):
        response = self.flota_client.post(
            self.list_url,
            {"name": "Org Flota", "cuit": "30-88888888-8", "billing_type": "prepaid"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# AuthorizedEmail (invitation) tests
# ---------------------------------------------------------------------------


class AuthorizedEmailTestCase(RoleAssignmentMixin, TestCase):
    """Tests for the AuthorizedEmail invitation flow and permissions."""

    LIST_URL = "/accounts/authorized-emails/"

    def setUp(self):
        # Holder user with Flota role and a holder account
        self.holder_user = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self.assign_role(self.holder_user, "Flota")
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )
        self.holder_account.balance = 500
        self.holder_account.save(update_fields=["balance"])
        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.holder_user)

        # Another Flota holder (different user)
        self.other_holder_user = CustomUser.objects.create_user(
            email="other-holder@example.com", password="pass1234"
        )
        self.assign_role(self.other_holder_user, "Flota")
        self.other_holder_account = Account.objects.get(
            user=self.other_holder_user, account_type="holder"
        )
        self.other_holder_client = APIClient()
        self.other_holder_client.force_authenticate(user=self.other_holder_user)

        # Gestor user
        self.gestor_user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self.assign_role(self.gestor_user, "Gestor")
        self.gestor_client = APIClient()
        self.gestor_client.force_authenticate(user=self.gestor_user)

        # Unauthenticated / plain user with no role
        self.plain_user = CustomUser.objects.create_user(
            email="plain@example.com", password="pass1234"
        )
        self.plain_client = APIClient()
        self.plain_client.force_authenticate(user=self.plain_user)

    def _create_invitation(self, email="unregistered@example.com", holder_account=None):
        holder_account = holder_account or self.holder_account
        return AuthorizedEmail.objects.create(
            email=email,
            dependent_of=holder_account,
            status="pending",
        )

    # --- model-level tests ---

    def test_create_invitation_model(self):
        inv = self._create_invitation()
        self.assertEqual(inv.status, "pending")
        self.assertEqual(inv.email, "unregistered@example.com")
        self.assertEqual(inv.dependent_of, self.holder_account)

    def test_cancel_invitation_model(self):
        inv = self._create_invitation()
        inv.cancel()
        inv.refresh_from_db()
        self.assertEqual(inv.status, "cancelled")

    def test_cancel_already_cancelled_raises(self):
        inv = self._create_invitation()
        inv.cancel()
        inv.refresh_from_db()
        with self.assertRaises(ValidationError):
            inv.cancel()

    def test_cancel_accepted_invitation_raises(self):
        inv = self._create_invitation()
        inv.status = "accepted"
        inv.save()
        with self.assertRaises(ValidationError):
            inv.cancel()

    def test_multiple_cancelled_same_email_allowed(self):
        """After removing the unique constraint, multiple cancelled records are allowed."""
        inv1 = self._create_invitation(email="dup@example.com")
        inv1.cancel()
        inv2 = self._create_invitation(email="dup@example.com")
        inv2.cancel()
        self.assertEqual(
            AuthorizedEmail.objects.filter(
                email="dup@example.com", status="cancelled"
            ).count(),
            2,
        )

    # --- API via add-dependent endpoint ---

    def test_invite_unregistered_user_creates_authorized_email(self):
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": "newuser@example.com",
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data.get("user_registered", True))
        self.assertTrue(
            AuthorizedEmail.objects.filter(
                email="newuser@example.com",
                dependent_of=self.holder_account,
                status="pending",
            ).exists()
        )

    def test_invite_same_unregistered_user_twice_fails(self):
        """Cannot create a second pending invitation for the same email+account."""
        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": "twice@example.com",
        }
        self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_reinvite_after_cancellation(self):
        """After cancelling an invitation, the same email can be invited again."""
        inv = self._create_invitation(email="reinvite@example.com")
        inv.cancel()

        payload = {
            "holder_account_id": self.holder_account.id,
            "dependent_email": "reinvite@example.com",
        }
        response = self.holder_client.post(
            "/actions/invitations/add-dependent/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            AuthorizedEmail.objects.filter(
                email="reinvite@example.com",
                dependent_of=self.holder_account,
                status="pending",
            ).count(),
            1,
        )

    # --- GET /accounts/authorized-emails/ ---

    def test_flota_user_sees_own_invitations(self):
        self._create_invitation(
            email="a@example.com", holder_account=self.holder_account
        )
        self._create_invitation(
            email="b@example.com", holder_account=self.other_holder_account
        )

        response = self.holder_client.get(self.LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [i["email"] for i in response.data]
        self.assertIn("a@example.com", emails)
        self.assertNotIn("b@example.com", emails)

    def test_gestor_can_filter_invitations_by_holder_account(self):
        """Gestores deben pasar ?dependent_of=<id> para ver las invitaciones de una cuenta."""
        self._create_invitation(
            email="a@example.com", holder_account=self.holder_account
        )
        self._create_invitation(
            email="b@example.com", holder_account=self.other_holder_account
        )

        # Con filtro: ve solo las de esa cuenta
        response = self.gestor_client.get(
            self.LIST_URL, {"dependent_of": self.holder_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [i["email"] for i in response.data]
        self.assertIn("a@example.com", emails)
        self.assertNotIn("b@example.com", emails)

        # Sin filtro: lista vacía (el Gestor no tiene cuentas propias)
        response = self.gestor_client.get(self.LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_plain_user_cannot_list_invitations(self):
        # El signal agrega a todos los usuarios al grupo Flota al crearse,
        # por lo que plain_user tiene acceso Flota (lista vacía propia)
        response = self.plain_client.get(self.LIST_URL)
        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN],
        )
        if response.status_code == status.HTTP_200_OK:
            self.assertEqual(response.data, [])

    # --- POST /accounts/authorized-emails/{id}/cancel/ ---

    def test_flota_user_can_cancel_own_invitation(self):
        inv = self._create_invitation()
        response = self.holder_client.post(f"{self.LIST_URL}{inv.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "cancelled")

    def test_flota_user_cannot_cancel_other_users_invitation(self):
        inv = self._create_invitation(
            email="other@example.com", holder_account=self.other_holder_account
        )
        response = self.holder_client.post(f"{self.LIST_URL}{inv.id}/cancel/")
        # 403 or 404 — not allowed either way
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )

    def test_gestor_can_cancel_any_invitation(self):
        """Gestor puede cancelar invitaciones de cualquier cuenta pasando ?dependent_of=<id>."""
        inv = self._create_invitation(
            email="x@example.com", holder_account=self.other_holder_account
        )
        response = self.gestor_client.post(
            f"{self.LIST_URL}{inv.id}/cancel/?dependent_of={self.other_holder_account.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "cancelled")

    def test_cancel_already_cancelled_returns_400(self):
        inv = self._create_invitation()
        inv.cancel()
        response = self.holder_client.post(f"{self.LIST_URL}{inv.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plain_user_cannot_cancel(self):
        inv = self._create_invitation()
        response = self.plain_client.post(f"{self.LIST_URL}{inv.id}/cancel/")
        # plain_user tiene Flota via signal pero no es dueño → 404 o 403
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
