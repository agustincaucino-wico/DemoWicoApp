from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Account, Plates
from locations.models import Country, Province, City
from operation.models import FuelLoadOperation, PaymentMethod
from stations.models import Station
from users.models import CustomUser
from users.roles import ROLES


class FuelLoadOperationAPITests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="Testland")
        self.province = Province.objects.create(
            name="Central Province", country=self.country
        )
        self.city = City.objects.create(name="Capitol City", province=self.province)

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

        self.user = CustomUser.objects.create_user(
            email="manager@example.com", password="pass1234"
        )
        self._assign_role(self.user, "Gestor")

        self.attendant = CustomUser.objects.create_user(
            email="attendant@example.com", password="pass1234"
        )
        self.other_attendant = CustomUser.objects.create_user(
            email="other-attendant@example.com", password="pass1234"
        )

        self.account = Account.objects.create(
            user=self.user, account_type="holder", balance=Decimal("0.00")
        )
        self.plate = Plates.objects.create(
            plate_number="AAA111",
            holder_account=self.account,
            start_date=timezone.now().date(),
        )
        self.payment_method = PaymentMethod.objects.create(name="Cash")

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.list_url = reverse("fuel-load-operations-list")

    def _assign_role(self, user, role_name):
        group, _ = Group.objects.get_or_create(name=role_name)
        permissions = Permission.objects.filter(codename__in=ROLES.get(role_name, []))
        group.permissions.set(permissions)
        user.groups.add(group)

    def _create_operation(self, **kwargs):
        defaults = {
            "account": self.account,
            "plate": self.plate,
            "station": self.station,
            "initial_amount": Decimal("10.00"),
            "status": FuelLoadOperation.STATUS_PENDING,
        }
        defaults.update(kwargs)
        return FuelLoadOperation.objects.create(**defaults)

    def test_create_operation_defaults_to_pending_and_sets_timestamp(self):
        payload = {
            "account": self.account.id,
            "plate": self.plate.id,
            "station": self.station.id,
            "initial_amount": "50.00",
            "payment_method": self.payment_method.id,
            "fill_full_tank": True,
        }

        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation = FuelLoadOperation.objects.get(id=response.data["id"])

        self.assertEqual(operation.status, FuelLoadOperation.STATUS_PENDING)
        self.assertIsNotNone(operation.timestamp_started)
        self.assertIsNone(operation.final_amount)
        self.assertEqual(operation.initial_amount, Decimal("50.00"))
        self.assertTrue(operation.fill_full_tank)
        self.assertEqual(operation.payment_method, self.payment_method)
        self.assertEqual(operation.account, self.account)

    def test_list_filters_by_station(self):
        op_station_one = self._create_operation(initial_amount=Decimal("15.00"))
        self._create_operation(
            station=self.other_station, initial_amount=Decimal("20.00")
        )

        response = self.client.get(self.list_url, {"station": self.station.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertSetEqual(returned_ids, {op_station_one.id})

    def test_list_filters_by_status_and_attendant(self):
        matching_op = self._create_operation(
            status=FuelLoadOperation.STATUS_IN_PROGRESS, attendant=self.attendant
        )
        self._create_operation(
            status=FuelLoadOperation.STATUS_IN_PROGRESS,
            attendant=self.other_attendant,
        )
        self._create_operation(
            status=FuelLoadOperation.STATUS_COMPLETED, attendant=self.attendant
        )

        response = self.client.get(
            self.list_url,
            {
                "status": FuelLoadOperation.STATUS_IN_PROGRESS,
                "attendant": self.attendant.id,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertSetEqual(returned_ids, {matching_op.id})

    def test_list_orders_by_timestamp_desc(self):
        older = self._create_operation(initial_amount=Decimal("15.00"))
        newer = self._create_operation(initial_amount=Decimal("25.00"))
        FuelLoadOperation.objects.filter(id=older.id).update(
            timestamp_started=timezone.now() - timedelta(hours=1)
        )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [item["id"] for item in response.data]
        self.assertEqual(returned_ids, [newer.id, older.id])

    def test_delete_operation_removes_instance(self):
        operation = self._create_operation()
        detail_url = reverse("fuel-load-operations-detail", args=[operation.id])

        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FuelLoadOperation.objects.filter(id=operation.id).exists())
