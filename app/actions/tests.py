from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import (
    Account,
    Company,
    DependentInvitation,
    Dependents,
    Organism,
    Plates,
)
from locations.models import Country, Province, City
from operation.models import FuelLoadOperation, ModifyFunds, Transfer
from stations.models import Station, StationAttendantAssignment
from users.models import CustomUser
from users.test_helpers import RoleAssignmentMixin
from utils import remito_pdf


class FuelLoadFlowTests(RoleAssignmentMixin, TestCase):
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
        self.holder_account = Account.objects.get(user=self.holder_user, account_type="holder")
        self.holder_account.balance = Decimal("100.00")
        self.holder_account.save()

        self.plate = Plates.objects.create(
            plate_number="ABC123",
            holder_account=self.holder_account,
            start_date=timezone.now().date(),
        )

        # Second holder for multi-user scenarios
        self.other_holder_user = CustomUser.objects.create_user(
            email="other-holder@example.com", password="pass1234"
        )
        self.other_holder_account = Account.objects.get(user=self.other_holder_user, account_type="holder")
        self.other_holder_account.balance = Decimal("100.00")
        self.other_holder_account.save()

        self.other_plate = Plates.objects.create(
            plate_number="XYZ789",
            holder_account=self.other_holder_account,
            start_date=timezone.now().date(),
        )

        # Playero (attendant) with assignment
        self.attendant_user = CustomUser.objects.create_user(
            email="playero@example.com", password="pass1234"
        )
        self.assign_role(self.attendant_user, "Playero")
        StationAttendantAssignment.objects.create(
            attendant=self.attendant_user,
            station=self.station,
            start_date=timezone.now().date(),
        )

        # Playero without assignment
        self.unassigned_attendant = CustomUser.objects.create_user(
            email="no-station@example.com", password="pass1234"
        )
        self.assign_role(self.unassigned_attendant, "Playero")

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
        self.holder_account = Account.objects.get(user=self.holder_user, account_type="holder")
        self.holder_account.balance = Decimal("100.00")
        self.holder_account.save()

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


class TransferBalanceTests(TestCase):
    """
    End-to-end tests for POST /actions/transfer-balance/ (holder -> dependent).

    Non-obvious behavior confirmed by reading the view:
      - The relationship check only runs when the SOURCE account is a holder
        (`if source_account.account_type == "holder"`). If the source is a
        dependent account, `is_related` stays False and the request is always
        rejected with 403 - so this endpoint is effectively holder -> dependent
        only, even though the source `.get` itself does not filter by type.
      - The relationship lookup is directional and active-only:
        Dependents(holder_account=source, dependent_account=destination,
        end_date__isnull=True). An ended relationship (end_date set) no longer
        qualifies.
      - There is no idempotency/dedup: the sole protection against replaying a
        transfer is the balance check. select_for_update guards concurrent
        drains but only matters under real DB concurrency, which is not
        exercised deterministically here.
    """

    URL = "/actions/transfer-balance/"

    def setUp(self):
        # Holder (source) - fetch the account auto-created by the post_save
        # signal, then fund it. A second holder cannot be baker.make'd for the
        # same user due to the one_holder_account_per_user constraint.
        self.holder_user = CustomUser.objects.create_user(
            email="transfer-holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )
        self.holder_account.balance = Decimal("1000.00")
        self.holder_account.save()

        # Dependent (destination) related to the holder, starts empty.
        self.dependent_user = CustomUser.objects.create_user(
            email="transfer-dependent@example.com", password="pass1234"
        )
        self.dependent_account = baker.make(
            Account,
            user=self.dependent_user,
            account_type="dependent",
            balance=Decimal("0.00"),
            is_active=True,
        )
        self.relation = baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.holder_user)

    def _payload(self, amount, source=None, destination=None):
        return {
            "source_account_id": source if source is not None else self.holder_account.id,
            "destination_account_id": (
                destination if destination is not None else self.dependent_account.id
            ),
            "amount": str(amount),
        }

    def test_valid_transfer_updates_both_balances_and_writes_audit_record(self):
        response = self.client.post(
            self.URL, self._payload(Decimal("300.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Transfer successful")

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("700.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("300.00"))

        transfers = Transfer.objects.filter(
            source_account=self.holder_account,
            destination_account=self.dependent_account,
        )
        self.assertEqual(transfers.count(), 1)
        self.assertEqual(transfers.first().amount, Decimal("300.00"))

    def test_insufficient_balance_is_rejected_with_no_state_change(self):
        response = self.client.post(
            self.URL, self._payload(Decimal("1500.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Saldo insuficiente", str(response.data))

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("1000.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("0.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_source_account_not_owned_by_requester_returns_403(self):
        """A user cannot transfer FROM an account that isn't theirs."""
        attacker = CustomUser.objects.create_user(
            email="transfer-attacker@example.com", password="pass1234"
        )
        attacker_client = APIClient()
        attacker_client.force_authenticate(user=attacker)

        response = attacker_client.post(
            self.URL, self._payload(Decimal("100.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.holder_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("1000.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_inactive_destination_account_returns_404(self):
        self.dependent_account.is_active = False
        self.dependent_account.save()

        response = self.client.post(
            self.URL, self._payload(Decimal("100.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.holder_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("1000.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_transfer_to_unrelated_dependent_is_rejected_403(self):
        """Destination is active but has no Dependents relationship with the source."""
        stranger_user = CustomUser.objects.create_user(
            email="transfer-stranger@example.com", password="pass1234"
        )
        unrelated_dependent = baker.make(
            Account,
            user=stranger_user,
            account_type="dependent",
            balance=Decimal("0.00"),
            is_active=True,
        )

        response = self.client.post(
            self.URL,
            self._payload(Decimal("100.00"), destination=unrelated_dependent.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("no están relacionadas", str(response.data))

        self.holder_account.refresh_from_db()
        unrelated_dependent.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("1000.00"))
        self.assertEqual(unrelated_dependent.balance, Decimal("0.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_transfer_over_ended_relationship_is_rejected_403(self):
        """An ended relationship (end_date set) no longer qualifies as related."""
        self.relation.end_date = timezone.now().date()
        self.relation.save()

        response = self.client.post(
            self.URL, self._payload(Decimal("100.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("1000.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("0.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_dependent_account_as_source_is_always_rejected_403(self):
        """
        The is_related check is gated on the source being a holder. A user who
        owns a dependent account and passes it as the source can never satisfy
        it, so the transfer is refused even toward a legitimately related
        account. Documents that this endpoint is holder-source only.
        """
        # The dependent_user owns their dependent_account; authenticate as them
        # and try to use it as the source.
        dependent_client = APIClient()
        dependent_client.force_authenticate(user=self.dependent_user)
        self.dependent_account.balance = Decimal("500.00")
        self.dependent_account.save()

        response = dependent_client.post(
            self.URL,
            self._payload(
                Decimal("100.00"),
                source=self.dependent_account.id,
                destination=self.holder_account.id,
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.dependent_account.refresh_from_db()
        self.holder_account.refresh_from_db()
        self.assertEqual(self.dependent_account.balance, Decimal("500.00"))
        self.assertEqual(self.holder_account.balance, Decimal("1000.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_invalid_amount_is_rejected_by_serializer(self):
        """amount below the serializer min_value (0.01) is a 400 with no effect."""
        response = self.client.post(
            self.URL, self._payload(Decimal("0.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)
        self.assertFalse(Transfer.objects.exists())

    def test_no_dedup_guard_replayed_transfer_only_stopped_by_balance(self):
        """
        There is no idempotency key: a second identical transfer succeeds if
        the balance still allows it, and is only blocked once the balance runs
        out. This documents that the balance check is the sole double-spend
        guard (select_for_update additionally protects concurrent drains, which
        isn't exercised here).
        """
        first = self.client.post(
            self.URL, self._payload(Decimal("600.00")), format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        # Replay the same transfer: 600 > remaining 400 -> rejected, no change.
        second = self.client.post(
            self.URL, self._payload(Decimal("600.00")), format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Saldo insuficiente", str(second.data))

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("400.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("600.00"))
        self.assertEqual(Transfer.objects.count(), 1)


class WithdrawFromDependentTests(TestCase):
    """
    End-to-end tests for POST /actions/withdraw-from-dependent/
    (dependent -> holder, the mirror of TransferBalance).

    Non-obvious behavior confirmed by reading the view: unlike
    TransferBalanceView, both `.get` lookups here filter by account_type
    (holder must be account_type="holder", dependent must be
    account_type="dependent"). A type mismatch on holder_account_id shares
    the same lookup (and user=request.user filter) as the ownership check,
    so it surfaces as 403, same as any other holder-ownership violation. A
    type mismatch on dependent_account_id is not covered here (see the
    module-level note on the ambiguous dependent_account lookup branch).
    """

    URL = "/actions/withdraw-from-dependent/"

    def setUp(self):
        self.holder_user = CustomUser.objects.create_user(
            email="withdraw-holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )
        self.holder_account.balance = Decimal("100.00")
        self.holder_account.save()

        self.dependent_user = CustomUser.objects.create_user(
            email="withdraw-dependent@example.com", password="pass1234"
        )
        self.dependent_account = baker.make(
            Account,
            user=self.dependent_user,
            account_type="dependent",
            balance=Decimal("500.00"),
            is_active=True,
        )
        self.relation = baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.holder_user)

    def _payload(self, amount, holder=None, dependent=None):
        return {
            "holder_account_id": holder if holder is not None else self.holder_account.id,
            "dependent_account_id": (
                dependent if dependent is not None else self.dependent_account.id
            ),
            "amount": str(amount),
        }

    def test_valid_withdrawal_updates_both_balances_and_writes_audit_record(self):
        response = self.client.post(
            self.URL, self._payload(Decimal("200.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.dependent_account.balance, Decimal("300.00"))
        self.assertEqual(self.holder_account.balance, Decimal("300.00"))

        transfers = Transfer.objects.filter(
            source_account=self.dependent_account,
            destination_account=self.holder_account,
        )
        self.assertEqual(transfers.count(), 1)
        self.assertEqual(transfers.first().amount, Decimal("200.00"))

    def test_insufficient_dependent_balance_is_rejected_with_no_state_change(self):
        response = self.client.post(
            self.URL, self._payload(Decimal("999.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Saldo insuficiente", str(response.data))

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("100.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("500.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_holder_account_not_owned_by_requester_returns_403(self):
        attacker = CustomUser.objects.create_user(
            email="withdraw-attacker@example.com", password="pass1234"
        )
        attacker_client = APIClient()
        attacker_client.force_authenticate(user=attacker)

        response = attacker_client.post(
            self.URL, self._payload(Decimal("100.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.dependent_account.refresh_from_db()
        self.assertEqual(self.dependent_account.balance, Decimal("500.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_holder_account_id_pointing_to_dependent_type_returns_403(self):
        """
        The holder lookup filters account_type="holder"; passing a
        dependent-type account id as holder_account_id fails that lookup
        rather than moving money the wrong direction. It shares the same
        DoesNotExist branch (and user=request.user filter) as ownership
        violations, so it's a 403, same as any other holder-ownership case.
        """
        response = self.client.post(
            self.URL,
            self._payload(Decimal("100.00"), holder=self.dependent_account.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Transfer.objects.exists())

    def test_withdraw_from_unrelated_dependent_is_rejected_403(self):
        stranger_user = CustomUser.objects.create_user(
            email="withdraw-stranger@example.com", password="pass1234"
        )
        unrelated_dependent = baker.make(
            Account,
            user=stranger_user,
            account_type="dependent",
            balance=Decimal("500.00"),
            is_active=True,
        )

        response = self.client.post(
            self.URL,
            self._payload(Decimal("100.00"), dependent=unrelated_dependent.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("no están relacionadas", str(response.data))

        self.holder_account.refresh_from_db()
        unrelated_dependent.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("100.00"))
        self.assertEqual(unrelated_dependent.balance, Decimal("500.00"))
        self.assertFalse(Transfer.objects.exists())

    def test_withdraw_over_ended_relationship_is_rejected_403(self):
        self.relation.end_date = timezone.now().date()
        self.relation.save()

        response = self.client.post(
            self.URL, self._payload(Decimal("100.00")), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.holder_account.refresh_from_db()
        self.dependent_account.refresh_from_db()
        self.assertEqual(self.holder_account.balance, Decimal("100.00"))
        self.assertEqual(self.dependent_account.balance, Decimal("500.00"))
        self.assertFalse(Transfer.objects.exists())


# ---------------------------------------------------------------------------
# get_account_movements access-control tests
# ---------------------------------------------------------------------------


class AccountMovementsAccessTests(TestCase):
    """
    End-to-end tests for GET /actions/user/movements/ access control.

    Behavior confirmed by reading the real code: get_account_movements does
    NOT use the shared _user_can_access_account helper - it reimplements the
    same idea inline with subtle differences. With ?account_id it first tries
    "the account is mine and active"; failing that it requires the requester
    to have an ACTIVE holder account plus an un-ended Dependents link to the
    target. Denials are 404s (two different messages), never 403. One quirk:
    when the relationship is active but the dependent account itself is
    deactivated, the final Account.objects.filter(id=..., is_active=True)
    comes back empty, so the response is 200 with an empty list rather than
    a denial.
    """

    URL = "/actions/user/movements/"

    def setUp(self):
        self.holder_user = CustomUser.objects.create_user(
            email="movements-holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )

        self.dependent_user = CustomUser.objects.create_user(
            email="movements-dependent@example.com", password="pass1234"
        )
        self.dependent_account = baker.make(
            Account,
            user=self.dependent_user,
            account_type="dependent",
            balance=Decimal("500.00"),
            is_active=True,
        )
        self.relation = baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            end_date=None,
        )

        self.unrelated_user = CustomUser.objects.create_user(
            email="movements-stranger@example.com", password="pass1234"
        )

        # One movement of each type visible on the dependent account:
        # a completed fuel load, a received transfer, and a recharge.
        self.fuel_load = baker.make(
            FuelLoadOperation,
            account=self.dependent_account,
            status=FuelLoadOperation.STATUS_COMPLETED,
            initial_amount=Decimal("30.00"),
            final_amount=Decimal("25.50"),
            timestamp_finished=timezone.now(),
            plate=None,
            fuel_type=None,
            attendant=None,
            payment_method=None,
        )
        self.transfer = baker.make(
            Transfer,
            source_account=self.holder_account,
            destination_account=self.dependent_account,
            amount=Decimal("100.00"),
        )
        self.recharge = baker.make(
            ModifyFunds,
            account=self.dependent_account,
            gestor=self.holder_user,
            amount=Decimal("200.00"),
            payment_method=None,
        )

        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.holder_user)
        self.dependent_client = APIClient()
        self.dependent_client.force_authenticate(user=self.dependent_user)
        self.unrelated_client = APIClient()
        self.unrelated_client.force_authenticate(user=self.unrelated_user)

    def test_user_sees_own_account_movements_by_account_id(self):
        response = self.dependent_client.get(
            self.URL, {"account_id": self.dependent_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        by_type = {m["type"]: m for m in response.data}
        self.assertEqual(
            set(by_type),
            {"fuel_load", "transfer_received", "balance_recharge"},
        )
        # Fuel loads are shown as negative amounts, preferring final_amount.
        self.assertEqual(Decimal(by_type["fuel_load"]["amount"]), Decimal("-25.50"))
        self.assertEqual(
            by_type["fuel_load"]["remito_url"],
            f"/actions/user/movements/fuel-load/{self.fuel_load.id}/remito/",
        )
        self.assertEqual(
            Decimal(by_type["transfer_received"]["amount"]), Decimal("100.00")
        )
        self.assertEqual(
            Decimal(by_type["balance_recharge"]["amount"]), Decimal("200.00")
        )

    def test_all_own_accounts_included_without_account_id(self):
        response = self.holder_client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # The holder's only movement is the transfer it sent; transfer_sent
        # entries are only generated for holder-type accounts.
        types = [m["type"] for m in response.data]
        self.assertEqual(types, ["transfer_sent"])
        self.assertEqual(Decimal(response.data[0]["amount"]), Decimal("-100.00"))

    def test_holder_can_view_active_dependents_movements(self):
        response = self.holder_client.get(
            self.URL, {"account_id": self.dependent_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {m["type"] for m in response.data},
            {"fuel_load", "transfer_received", "balance_recharge"},
        )

    def test_unrelated_user_cannot_view_dependents_movements(self):
        response = self.unrelated_client.get(
            self.URL, {"account_id": self.dependent_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("no tienes permiso", response.data["error"])

    def test_requester_without_active_holder_account_gets_404(self):
        # Deactivating the stranger's own holder account removes the only
        # path into the dependent-relationship branch entirely.
        stranger_holder = Account.objects.get(
            user=self.unrelated_user, account_type="holder"
        )
        stranger_holder.is_active = False
        stranger_holder.save()

        response = self.unrelated_client.get(
            self.URL, {"account_id": self.dependent_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("no te pertenece", response.data["error"])

    def test_ended_relationship_denies_holder_access(self):
        self.relation.end_date = timezone.now().date()
        self.relation.save()

        response = self.holder_client.get(
            self.URL, {"account_id": self.dependent_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_dependent_account_returns_empty_list_not_404(self):
        """
        Quirk pinned on purpose: with the relationship still active but the
        dependent account deactivated, the access check passes and the final
        is_active=True fetch just comes back empty - a 200 with no movements,
        unlike every other unauthorized/invalid case which 404s.
        """
        self.dependent_account.is_active = False
        self.dependent_account.save()

        response = self.holder_client.get(
            self.URL, {"account_id": self.dependent_account.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


# ---------------------------------------------------------------------------
# get_fuel_load_remito access-control tests
# ---------------------------------------------------------------------------


class FuelLoadRemitoAccessTests(TestCase):
    """
    End-to-end tests for GET /actions/user/movements/fuel-load/<id>/remito/.

    This endpoint DOES use _user_can_access_account: active account AND
    (owner, OR target is dependent-type + requester has an active holder
    account with an un-ended Dependents link). Check order confirmed from the
    code: 404 unknown operation -> 400 not-completed -> 403 no access. The
    PDF branch depends on account.company: set -> empresa builder, else
    personal builder.
    """

    def setUp(self):
        self.holder_user = CustomUser.objects.create_user(
            email="remito-holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )

        self.dependent_user = CustomUser.objects.create_user(
            email="remito-dependent@example.com", password="pass1234"
        )
        self.dependent_account = baker.make(
            Account,
            user=self.dependent_user,
            account_type="dependent",
            balance=Decimal("500.00"),
            is_active=True,
        )
        self.relation = baker.make(
            Dependents,
            holder_account=self.holder_account,
            dependent_account=self.dependent_account,
            end_date=None,
        )

        self.unrelated_user = CustomUser.objects.create_user(
            email="remito-stranger@example.com", password="pass1234"
        )

        def make_load(account, load_status=FuelLoadOperation.STATUS_COMPLETED):
            return baker.make(
                FuelLoadOperation,
                account=account,
                status=load_status,
                initial_amount=Decimal("40.00"),
                final_amount=Decimal("38.20"),
                timestamp_finished=timezone.now(),
                plate=None,
                fuel_type=None,
                attendant=None,
                payment_method=None,
            )

        self.dependent_load = make_load(self.dependent_account)
        self.holder_load = make_load(self.holder_account)
        self.pending_load = make_load(
            self.dependent_account, FuelLoadOperation.STATUS_PENDING
        )

        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.holder_user)
        self.dependent_client = APIClient()
        self.dependent_client.force_authenticate(user=self.dependent_user)
        self.unrelated_client = APIClient()
        self.unrelated_client.force_authenticate(user=self.unrelated_user)

    def _url(self, operation_id):
        return f"/actions/user/movements/fuel-load/{operation_id}/remito/"

    def _assert_pdf(self, response, operation_id):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(
            f'filename="remito_carga_{operation_id}.pdf"',
            response["Content-Disposition"],
        )
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_owner_downloads_own_remito_with_personal_pdf(self):
        # Spy on the builder (wrapping the real one) to pin down which PDF
        # branch runs; the request itself still goes end-to-end.
        with patch(
            "actions.views.build_fuel_load_remito_pdf",
            wraps=remito_pdf.build_fuel_load_remito_pdf,
        ) as personal_builder:
            response = self.dependent_client.get(self._url(self.dependent_load.id))

        self._assert_pdf(response, self.dependent_load.id)
        personal_builder.assert_called_once()

    def test_holder_downloads_dependents_remito(self):
        response = self.holder_client.get(self._url(self.dependent_load.id))
        self._assert_pdf(response, self.dependent_load.id)

    def test_company_account_uses_empresa_pdf(self):
        organism = baker.make(Organism, cuit="30-11111111-1")
        company = baker.make(
            Company,
            organism=organism,
            cuit="30-22222222-2",
            tax_condition="responsable_inscripto",
        )
        self.holder_account.company = company
        self.holder_account.save()

        with patch(
            "actions.views.build_fuel_load_remito_empresa_pdf",
            wraps=remito_pdf.build_fuel_load_remito_empresa_pdf,
        ) as empresa_builder:
            response = self.holder_client.get(self._url(self.holder_load.id))

        self._assert_pdf(response, self.holder_load.id)
        empresa_builder.assert_called_once()

    def test_unrelated_user_denied_dependents_remito(self):
        response = self.unrelated_client.get(self._url(self.dependent_load.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unrelated_user_denied_holder_remito(self):
        # Exercises the account_type != "dependent" early-return: holder-type
        # accounts are only ever accessible to their owner, so having a
        # holder account of one's own doesn't help the stranger here.
        response = self.unrelated_client.get(self._url(self.holder_load.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_incomplete_operation_returns_400_before_access_check(self):
        """
        The completed-status check runs BEFORE the ownership check, so even a
        totally unrelated user gets a 400 (not 403) for a pending operation -
        the endpoint confirms the operation exists and isn't finished to
        someone with no right to know either fact.
        """
        for client in (self.dependent_client, self.unrelated_client):
            response = client.get(self._url(self.pending_load.id))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("completadas", response.data["error"])

    def test_nonexistent_operation_returns_404(self):
        response = self.dependent_client.get(self._url(999999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_of_deactivated_account_is_denied(self):
        """
        _user_can_access_account requires account.is_active before even the
        owner check, so deactivating an account cuts off the owner's access
        to receipts for their own past purchases.
        """
        self.dependent_account.is_active = False
        self.dependent_account.save()

        response = self.dependent_client.get(self._url(self.dependent_load.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Invitation lifecycle tests
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitationLifecycleTests(TestCase):
    """
    End-to-end tests for the dependent-invitation flow:
    POST /actions/invitations/create/, /actions/invitations/respond/<id>/ and
    /actions/invitations/cancel/.

    Ownership checks confirmed from the code: create validates the holder
    account belongs to the requester (serializer), respond compares the
    invitation's dependent_email case-insensitively against the requesting
    user's email, and cancel re-resolves the holder account with
    user=request.user. respond's check order is 404 (unknown id) -> 403 (not
    yours) -> 400 (not pending). Accepting creates a brand-new dependent
    Account (balance 0), the Dependents link, and assigns the Flota group.
    """

    CREATE_URL = "/actions/invitations/create/"
    CANCEL_URL = "/actions/invitations/cancel/"

    def _respond_url(self, invitation_id):
        return f"/actions/invitations/respond/{invitation_id}/"

    def setUp(self):
        self.holder_user = CustomUser.objects.create_user(
            email="invite-holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )
        self.invitee_user = CustomUser.objects.create_user(
            email="invite-target@example.com", password="pass1234"
        )
        self.other_user = CustomUser.objects.create_user(
            email="invite-bystander@example.com", password="pass1234"
        )
        # The Flota group exists from a data migration, and the CustomUser
        # post_save signal auto-assigns it to every new user. Strip it from
        # the invitee so the role-assignment assertion on accept is
        # meaningful.
        self.flota_group = Group.objects.get(name="Flota")
        self.invitee_user.groups.remove(self.flota_group)

        self.holder_client = APIClient()
        self.holder_client.force_authenticate(user=self.holder_user)
        self.invitee_client = APIClient()
        self.invitee_client.force_authenticate(user=self.invitee_user)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other_user)

    def _make_invitation(self):
        return DependentInvitation.objects.create(
            holder_account=self.holder_account,
            dependent_email=self.invitee_user.email,
        )

    # --- create ------------------------------------------------------------

    def test_create_invitation_success(self):
        response = self.holder_client.post(
            self.CREATE_URL,
            {
                "holder_account_id": self.holder_account.id,
                "dependent_email": self.invitee_user.email,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invitation = DependentInvitation.objects.get(
            holder_account=self.holder_account,
            dependent_email=self.invitee_user.email,
        )
        self.assertEqual(invitation.status, "pending")
        # The invitee actually got notified.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.invitee_user.email])

    def test_create_invitation_with_foreign_holder_account_rejected(self):
        response = self.other_client.post(
            self.CREATE_URL,
            {
                "holder_account_id": self.holder_account.id,
                "dependent_email": self.invitee_user.email,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no te pertenece", str(response.data))
        self.assertFalse(DependentInvitation.objects.exists())

    # --- respond -----------------------------------------------------------

    def test_accept_creates_dependent_account_relationship_and_role(self):
        invitation = self._make_invitation()
        self.assertFalse(
            self.invitee_user.groups.filter(name="Flota").exists()
        )

        response = self.invitee_client.post(
            self._respond_url(invitation.id), {"action": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertIsNotNone(invitation.response_date)

        dependent_account = Account.objects.get(
            user=self.invitee_user, account_type="dependent"
        )
        self.assertEqual(dependent_account.balance, Decimal("0"))
        self.assertTrue(
            Dependents.objects.filter(
                holder_account=self.holder_account,
                dependent_account=dependent_account,
                end_date__isnull=True,
            ).exists()
        )
        self.assertTrue(self.invitee_user.groups.filter(name="Flota").exists())

    def test_reject_marks_invitation_without_creating_anything(self):
        invitation = self._make_invitation()

        response = self.invitee_client.post(
            self._respond_url(invitation.id), {"action": "reject"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "rejected")
        self.assertFalse(
            Account.objects.filter(
                user=self.invitee_user, account_type="dependent"
            ).exists()
        )
        self.assertFalse(Dependents.objects.exists())

    def test_respond_to_anothers_invitation_forbidden(self):
        invitation = self._make_invitation()

        response = self.other_client.post(
            self._respond_url(invitation.id), {"action": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")
        self.assertFalse(Dependents.objects.exists())

    def test_respond_twice_returns_400(self):
        invitation = self._make_invitation()
        first = self.invitee_client.post(
            self._respond_url(invitation.id), {"action": "reject"}, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        again = self.invitee_client.post(
            self._respond_url(invitation.id), {"action": "accept"}, format="json"
        )
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "rejected")

    def test_respond_nonexistent_invitation_returns_404(self):
        response = self.invitee_client.post(
            self._respond_url(999999), {"action": "accept"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- cancel ------------------------------------------------------------

    def test_cancel_pending_invitation(self):
        invitation = self._make_invitation()

        response = self.holder_client.post(
            self.CANCEL_URL,
            {
                "holder_account_id": self.holder_account.id,
                "dependent_email": self.invitee_user.email,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "cancelled")

        # A cancelled invitation can no longer be accepted.
        late_accept = self.invitee_client.post(
            self._respond_url(invitation.id), {"action": "accept"}, format="json"
        )
        self.assertEqual(late_accept.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_with_foreign_holder_account_returns_404(self):
        invitation = self._make_invitation()

        response = self.other_client.post(
            self.CANCEL_URL,
            {
                "holder_account_id": self.holder_account.id,
                "dependent_email": self.invitee_user.email,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("does not belong to you", str(response.data))

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")
