from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Account, Plates, Dependents
from locations.models import Country, Province, City
from operation.models import FuelLoadOperation
from stations.models import Station, StationAttendantAssignment
from users.models import CustomUser
from users.roles import ROLES


class FuelLoadFlowTests(TestCase):
    def setUp(self):
        # Location setup
        self.country = Country.objects.create(name="Testland")
        self.province = Province.objects.create(
            name="Central Province", country=self.country
        )
        self.city = City.objects.create(name="Capitol City", province=self.province)

        # Stations
        self.station = Station.objects.create(
            name="Station One",
            province=self.province,
            city=self.city,
            street="Main",
            street_number="1",
        )
        self.other_station = Station.objects.create(
            name="Station Two",
            province=self.province,
            city=self.city,
            street="Second",
            street_number="2",
        )

        # Holder user + account with balance
        self.holder_user = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.create(
            user=self.holder_user, account_type="holder", balance=Decimal("100.00")
        )

        self.plate = Plates.objects.create(
            plate_number="ABC123",
            holder_account=self.holder_account,
            start_date=timezone.now().date(),
        )

        # Second holder for multi-user scenarios
        self.other_holder_user = CustomUser.objects.create_user(
            email="other-holder@example.com", password="pass1234"
        )
        self.other_holder_account = Account.objects.create(
            user=self.other_holder_user,
            account_type="holder",
            balance=Decimal("100.00"),
        )

        self.other_plate = Plates.objects.create(
            plate_number="XYZ789",
            holder_account=self.other_holder_account,
            start_date=timezone.now().date(),
        )

        # Playero (attendant) with assignment
        self.attendant_user = CustomUser.objects.create_user(
            email="playero@example.com", password="pass1234"
        )
        self._assign_role(self.attendant_user, "Playero")
        StationAttendantAssignment.objects.create(
            attendant=self.attendant_user,
            station=self.station,
            start_date=timezone.now().date(),
        )

        # Playero without assignment
        self.unassigned_attendant = CustomUser.objects.create_user(
            email="no-station@example.com", password="pass1234"
        )
        self._assign_role(self.unassigned_attendant, "Playero")

        # API clients
        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.holder_user)

        self.other_holder_client = APIClient()
        self.other_holder_client.force_authenticate(user=self.other_holder_user)

        self.attendant_client = APIClient()
        self.attendant_client.force_authenticate(user=self.attendant_user)

        self.unassigned_attendant_client = APIClient()
        self.unassigned_attendant_client.force_authenticate(
            user=self.unassigned_attendant
        )

    def _assign_role(self, user, role_name):
        group, _ = Group.objects.get_or_create(name=role_name)
        permissions = Permission.objects.filter(codename__in=ROLES.get(role_name, []))
        group.permissions.set(permissions)
        user.groups.add(group)

    def _initiate_operation(self, client=None, account=None, station=None, amount="30"):
        client = client or self.holder_client
        account = account or self.holder_account
        station_id = station or self.station.id
        payload = {
            "account": account.id,
            "amount": amount,
            "station": station_id,
            "plate": self.plate.id,
        }
        return client.post(
            "/actions/fuel-load/initiate-fuel-load/", payload, format="json"
        )

    def test_full_flow_attendant_completes_load(self):
        initiate_response = self._initiate_operation(amount="40.00")
        self.assertEqual(initiate_response.status_code, status.HTTP_201_CREATED)
        operation_id = initiate_response.data["id"]

        pending_response = self.attendant_client.get(
            "/actions/fuel-load/attendant/pending-loads/"
        )
        self.assertEqual(pending_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any(
                item["id_operation"] == operation_id
                for item in pending_response.data["pending_loads"]
            )
        )

        start_response = self.attendant_client.post(
            "/actions/fuel-load/attendant/start-fuel-load/",
            {"id_operation": operation_id},
            format="json",
        )
        self.assertEqual(start_response.status_code, status.HTTP_200_OK)
        operation = FuelLoadOperation.objects.get(id=operation_id)
        self.assertEqual(operation.status, FuelLoadOperation.STATUS_IN_PROGRESS)
        self.assertEqual(operation.attendant, self.attendant_user)

        status_response = self.attendant_client.get(
            f"/actions/fuel-load/get-fuel-load-status/{operation_id}/"
        )
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            status_response.data["status"], FuelLoadOperation.STATUS_IN_PROGRESS
        )

        complete_response = self.attendant_client.post(
            "/actions/fuel-load/attendant/confirm-load/",
            {"id_operation": operation_id, "final_amount": "25.00"},
            format="json",
        )
        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        operation.refresh_from_db()
        self.holder_account.refresh_from_db()
        self.assertEqual(operation.status, FuelLoadOperation.STATUS_COMPLETED)
        self.assertEqual(operation.final_amount, Decimal("25.00"))
        self.assertEqual(self.holder_account.balance, Decimal("75.00"))
        self.assertIsNotNone(operation.timestamp_finished)

        last_status = self.holder_client.get(
            "/actions/fuel-load/check-last-operation-status/"
        )
        self.assertEqual(last_status.status_code, status.HTTP_200_OK)
        self.assertEqual(last_status.data["status"], FuelLoadOperation.STATUS_COMPLETED)
        self.assertEqual(last_status.data["final_amount"], "25.00")

    def test_initiate_without_enough_balance_records_no_balance(self):
        response = self._initiate_operation(amount="150.00")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        operation = FuelLoadOperation.objects.latest("timestamp_started")
        self.assertEqual(operation.status, FuelLoadOperation.STATUS_NO_BALANCE)
        self.assertEqual(operation.initial_amount, Decimal("150.00"))

    def test_user_cancel_pending_operation(self):
        response = self._initiate_operation(amount="20.00")
        operation_id = response.data["id"]

        cancel_response = self.holder_client.post(
            f"/actions/fuel-load/cancel-fuel-load/{operation_id}/",
            {"message": "No longer needed"},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        operation = FuelLoadOperation.objects.get(id=operation_id)
        self.assertEqual(operation.status, FuelLoadOperation.CANCELED_BY_USER)
        self.assertEqual(operation.comments, "No longer needed")
        self.assertIsNotNone(operation.timestamp_finished)

    def test_user_cancel_waiting_for_attendant(self):
        self._initiate_operation(amount="15.00")
        response = self.holder_client.post(
            "/actions/fuel-load/cancel-waiting/", {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        operation = FuelLoadOperation.objects.latest("timestamp_started")
        self.assertEqual(operation.status, FuelLoadOperation.WAITING_CANCELED)
        self.assertIsNotNone(operation.timestamp_finished)

    def test_attendant_cannot_start_without_assignment(self):
        response = self._initiate_operation(amount="30.00")
        operation_id = response.data["id"]

        start_response = self.unassigned_attendant_client.post(
            "/actions/fuel-load/attendant/start-fuel-load/",
            {"id_operation": operation_id},
            format="json",
        )
        self.assertEqual(start_response.status_code, status.HTTP_400_BAD_REQUEST)
        operation = FuelLoadOperation.objects.get(id=operation_id)
        self.assertEqual(operation.status, FuelLoadOperation.STATUS_PENDING)

    def test_attendant_cancel_in_progress_operation(self):
        response = self._initiate_operation(amount="35.00")
        operation_id = response.data["id"]
        # Move to in-progress
        self.attendant_client.post(
            "/actions/fuel-load/attendant/start-fuel-load/",
            {"id_operation": operation_id},
            format="json",
        )

        cancel_response = self.attendant_client.post(
            f"/actions/fuel-load/attendant/cancel-load/{operation_id}/",
            {"message": "Pump issue"},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        operation = FuelLoadOperation.objects.get(id=operation_id)
        self.assertEqual(operation.status, FuelLoadOperation.CANCELED_BY_ATENDEE)
        self.assertEqual(operation.comments, "Pump issue")
        self.assertIsNotNone(operation.timestamp_finished)

    def test_pending_loads_are_filtered_by_attendant_station(self):
        first_op = self._initiate_operation(amount="10.00", station=self.station.id)
        self.assertEqual(first_op.status_code, status.HTTP_201_CREATED)

        # Create a pending operation at another station for a different user
        second_payload = {
            "account": self.other_holder_account.id,
            "amount": "15.00",
            "station": self.other_station.id,
            "plate": self.other_plate.id,
        }
        second_response = self.other_holder_client.post(
            "/actions/fuel-load/initiate-fuel-load/", second_payload, format="json"
        )
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)

        response = self.attendant_client.get(
            "/actions/fuel-load/attendant/pending-loads/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id_operation"] for item in response.data["pending_loads"]}
        self.assertIn(first_op.data["id"], returned_ids)
        self.assertNotIn(second_response.data["id"], returned_ids)


class RemoveDependentTests(TestCase):
    def setUp(self):
        # Holder user + account
        self.holder_user = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.create(
            user=self.holder_user, account_type="holder", balance=Decimal("100.00")
        )

        # Dependent user + account
        self.dependent_user = CustomUser.objects.create_user(
            email="dependent@example.com", password="pass1234"
        )
        self.dependent_account = Account.objects.create(
            user=self.dependent_user,
            account_type="dependent",
            balance=Decimal("50.00"),
            is_active=True,
        )

        # Link them
        self.dependent_relation = Dependents.objects.create(
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            start_date=timezone.now().date(),
        )

        # API client
        self.client = APIClient()
        self.client.force_authenticate(user=self.holder_user)

    def test_remove_dependent_sets_inactive(self):
        """
        Test that removing a dependent sets the account to inactive
        and transfers balance.
        """
        url = "/actions/remove-dependent/"
        data = {
            "holder_account_id": self.holder_account.id,
            "dependent_account_id": self.dependent_account.id,
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh accounts
        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.dependent_relation.refresh_from_db()

        # Check balance transfer
        self.assertEqual(self.holder_account.balance, Decimal("150.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("0.00"))

        # Check relationship ended
        self.assertIsNotNone(self.dependent_relation.end_date)

        # Check account is inactive
        self.assertFalse(self.dependent_account.is_active)

    def test_inactive_dependent_not_in_user_info(self):
        """
        Test that inactive dependent accounts are not returned in UserInfoView.
        """
        # First verify it is returned
        url = "/actions/info/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check dependents list
        dependents = response.data["dependents"]
        self.assertEqual(len(dependents), 1)
        self.assertEqual(
            dependents[0]["dependent_account"]["id"], self.dependent_account.id
        )

        # Now remove the dependent
        self.client.post(
            "/actions/remove-dependent/",
            {
                "holder_account_id": self.holder_account.id,
                "dependent_account_id": self.dependent_account.id,
            },
            format="json",
        )

        # Verify it is NOT returned
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        dependents = response.data["dependents"]
        self.assertEqual(len(dependents), 0)
