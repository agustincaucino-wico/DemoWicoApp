from decimal import Decimal
from datetime import timedelta

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
from users.test_helpers import RoleAssignmentMixin


class FuelLoadOperationAPITests(RoleAssignmentMixin, TestCase):
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
        self.assign_role(self.user, "Gestor")

        self.attendant = CustomUser.objects.create_user(
            email="attendant@example.com", password="pass1234"
        )
        self.other_attendant = CustomUser.objects.create_user(
            email="other-attendant@example.com", password="pass1234"
        )

        # El signal post_save de accounts crea automáticamente la cuenta holder
        # al crear el usuario; la obtenemos en lugar de intentar crear otra.
        self.account = Account.objects.get(user=self.user, account_type="holder")
        self.plate = Plates.objects.create(
            plate_number="AAA111",
            holder_account=self.account,
            start_date=timezone.now().date(),
        )
        self.payment_method = PaymentMethod.objects.create(name="Cash")

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.list_url = reverse("fuel-load-operations-list")

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

    def test_fuel_operation_amount_max_limit_15_digits(self):
        """Test that fuel operation amounts can support up to 15 digits (13 integer + 2 decimal)"""
        # Test maximum valid amount: 9,999,999,999,999.99
        max_amount = Decimal("9999999999999.99")
        payload = {
            "account": self.account.id,
            "plate": self.plate.id,
            "station": self.station.id,
            "initial_amount": str(max_amount),
            "payment_method": self.payment_method.id,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation = FuelLoadOperation.objects.get(id=response.data["id"])
        self.assertEqual(operation.initial_amount, max_amount)

        # Test large valid amount with 13 integer digits
        large_amount = Decimal("1234567890123.45")
        payload["initial_amount"] = str(large_amount)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation = FuelLoadOperation.objects.get(id=response.data["id"])
        self.assertEqual(operation.initial_amount, large_amount)

    def test_balance_recharge_max_limit_validation(self):
        """Test that balance recharge request validates max amount of 15 digits"""
        from operation.serializers import BalanceRechargeRequestCreateSerializer
        from decimal import Decimal

        # Create a mock request object with the user
        class MockRequest:
            def __init__(self, user):
                self.user = user

        # Test maximum valid amount: 9,999,999,999,999.99 (just validate amount field)
        max_amount = Decimal("9999999999999.99")
        serializer = BalanceRechargeRequestCreateSerializer(
            context={"request": MockRequest(self.user)}
        )
        # Validate just the amount field
        validated_amount = serializer.validate_amount(max_amount)
        self.assertEqual(validated_amount, max_amount)

        # Test amount exceeding maximum: 10,000,000,000,000.00
        from rest_framework.exceptions import ValidationError

        over_max = Decimal("10000000000000.00")
        serializer = BalanceRechargeRequestCreateSerializer(
            context={"request": MockRequest(self.user)}
        )
        with self.assertRaises(ValidationError) as context:
            serializer.validate_amount(over_max)
        self.assertIn("exceder", str(context.exception).lower())


class PaginationBehaviorTests(RoleAssignmentMixin, TestCase):
    """
    Verifica el comportamiento retrocompatible de ConditionalPageNumberPagination.

    Regla clave:
      - Sin ?page ni ?page_size → response.data es una lista directa (array).
      - Con ?page=N → response.data tiene la forma { count, next, previous, results }.
    """

    def setUp(self):
        self.country = Country.objects.create(name="PagTestland")
        self.province = Province.objects.create(
            name="PagProvince", country=self.country
        )
        self.city = City.objects.create(name="PagCity", province=self.province)
        self.station = Station.objects.create(
            name="PagStation",
            province=self.province,
            city=self.city,
            street="Pag St",
            street_number="1",
        )
        self.user = CustomUser.objects.create_user(
            email="pagtest@example.com", password="pass1234"
        )
        self.assign_role(self.user, "Gestor")
        # El signal post_save de accounts crea automáticamente la cuenta holder
        # al crear el usuario; la obtenemos en lugar de intentar crear otra.
        self.account = Account.objects.get(user=self.user, account_type="holder")
        self.plate = Plates.objects.create(
            plate_number="PAG001",
            holder_account=self.account,
            start_date=timezone.now().date(),
        )
        self.payment_method = PaymentMethod.objects.create(name="TestCash")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.list_url = reverse("fuel-load-operations-list")

        # Crear 30 operaciones para que haya más de una página (page_size=25)
        for i in range(30):
            FuelLoadOperation.objects.create(
                account=self.account,
                plate=self.plate,
                station=self.station,
                initial_amount=Decimal(f"{i + 1}.00"),
                status=FuelLoadOperation.STATUS_PENDING,
            )

    def test_sin_page_param_devuelve_lista_directa(self):
        """Sin ?page el response debe ser un array directo (retrocompatibilidad)."""
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(
            response.data,
            list,
            "Sin ?page el response debe ser una lista directa, no un objeto paginado.",
        )
        # Todos los registros deben estar presentes
        self.assertEqual(len(response.data), 30)

    def test_con_page_param_devuelve_formato_paginado(self):
        """Con ?page=1 el response debe tener count, next, previous, results."""
        response = self.client.get(self.list_url, {"page": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 30)
        # Primera página tiene 25 resultados (page_size=25)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertIsNone(response.data["previous"])
        self.assertIsNotNone(response.data["next"])

    def test_segunda_pagina_tiene_resultados_restantes(self):
        """La segunda página debe tener los 5 registros restantes."""
        response = self.client.get(self.list_url, {"page": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIsNotNone(response.data["previous"])
        self.assertIsNone(response.data["next"])

    def test_page_size_custom(self):
        """?page_size=10 debe devolver exactamente 10 resultados por página."""
        response = self.client.get(self.list_url, {"page": 1, "page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(response.data["count"], 30)

    def test_solo_page_size_activa_paginacion(self):
        """Enviar solo ?page_size (sin ?page) también debe activar la paginación."""
        response = self.client.get(self.list_url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 10)

    def test_page_size_max_no_superable(self):
        """?page_size mayor que el máximo (200) debe limitarse a 200."""
        response = self.client.get(self.list_url, {"page": 1, "page_size": 9999})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Hay 30 registros, todos caben dentro del máximo de 200
        self.assertEqual(len(response.data["results"]), 30)
