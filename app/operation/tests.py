import shutil
import tempfile
from decimal import Decimal
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Account, Plates
from appconfig.models import AppConfig, BonificationTier
from locations.models import Country, Province, City
from operation.models import (
    BalanceRechargeRequest,
    FuelLoadOperation,
    ModifyFunds,
    PaymentMethod,
)
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


_RECHARGE_MEDIA_ROOT = tempfile.mkdtemp(prefix="wico-test-recharge-media-")


@override_settings(MEDIA_ROOT=_RECHARGE_MEDIA_ROOT)
class BalanceRechargeRequestFlowTests(RoleAssignmentMixin, TestCase):
    """
    End-to-end tests for the balance recharge request flow, hitting the real
    /operations/recharge-requests/ endpoints (create, approve, reject) instead
    of calling serializer/view methods directly.

    Covers the create -> pending -> approve/reject lifecycle, the
    fuel_price/BonificationTier bonus math inside approve() (including two
    non-obvious behaviors found by reading the view: tiers are matched by
    "last qualifying tier wins" rather than "first match", and the bonus is
    truncated - not rounded - to whole pesos), the ModifyFunds audit trail,
    permission enforcement, and the not-pending-anymore guard on both
    approve and reject (which also guards against double-crediting).
    """

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_RECHARGE_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="recharge-requester@example.com", password="pass1234"
        )
        self.gestor = CustomUser.objects.create_user(
            email="recharge-gestor@example.com", password="pass1234"
        )
        self.assign_role(self.gestor, "Gestor")

        # El signal post_save de accounts crea automáticamente la cuenta
        # holder al crear el usuario; la obtenemos en lugar de crear otra.
        self.account = Account.objects.get(user=self.user, account_type="holder")

        self.user_client = APIClient()
        self.user_client.force_authenticate(user=self.user)

        self.gestor_client = APIClient()
        self.gestor_client.force_authenticate(user=self.gestor)

        self.list_url = reverse("recharge-requests-list")

    def _proof_file(self):
        """A fresh upload each time - Django's UploadedFile can only be read once."""
        return SimpleUploadedFile(
            "comprobante.png", b"fake-file-bytes", content_type="image/png"
        )

    def _approve_url(self, recharge_request):
        return reverse("recharge-requests-approve", args=[recharge_request.id])

    def _reject_url(self, recharge_request):
        return reverse("recharge-requests-reject", args=[recharge_request.id])

    def _create_pending_request(self, amount):
        return BalanceRechargeRequest.objects.create(
            account=self.account,
            requested_by=self.user,
            amount=amount,
            transfer_proof=self._proof_file(),
        )

    def _configure_bonification(self, fuel_price, tiers=()):
        """
        appconfig migrations 0005/0007 seed a real AppConfig singleton
        (fuel_price=1928.00) and 4 default BonificationTier rows into the
        test database - that seed data is committed before any test
        transaction starts, so per-test rollback doesn't clear it. Reset
        both to a known, isolated state instead of fighting the seed data or
        (worse) coupling test assertions to it.
        """
        BonificationTier.objects.all().delete()
        config = AppConfig.get_config()
        config.fuel_price = fuel_price
        config.save()
        for tier_kwargs in tiers:
            BonificationTier.objects.create(**tier_kwargs)

    # --- create (user-facing) -------------------------------------------

    def test_user_requests_recharge_creates_pending_request(self):
        payload = {
            "account": self.account.id,
            "amount": "1500.00",
            "transfer_proof": self._proof_file(),
            "comments": "Transferencia desde Banco Test",
        }
        response = self.user_client.post(self.list_url, payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # The create serializer's fields don't include "id", so look the
        # request up directly instead of reading it from the response.
        recharge_request = BalanceRechargeRequest.objects.get(
            requested_by=self.user, amount=Decimal("1500.00")
        )
        self.assertEqual(recharge_request.status, BalanceRechargeRequest.STATUS_PENDING)
        self.assertTrue(recharge_request.is_pending)
        self.assertEqual(recharge_request.requested_by, self.user)
        self.assertEqual(recharge_request.account, self.account)
        self.assertEqual(recharge_request.amount, Decimal("1500.00"))
        # Balance must not move until a Gestor approves it.
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("0.00"))

    # --- approve: exact balance + bonification math ----------------------

    def test_admin_approves_credits_exact_balance_using_highest_qualifying_tier(self):
        """
        Three tiers, ordered ascending. The request amount qualifies for the
        first two tiers but not the third. approve() iterates all tiers
        without breaking early and keeps overwriting `applicable_tier` on
        every match, so the LAST (highest) qualifying tier wins - not the
        first one reached. This test fails if that assumption is wrong.
        """
        self._configure_bonification(
            fuel_price=Decimal("1200.00"),
            tiers=[
                {
                    "order": 1,
                    "min_liters": Decimal("100.00"),
                    "bonus_percent": Decimal("5.00"),
                },
                {
                    "order": 2,
                    "min_liters": Decimal("300.00"),
                    "bonus_percent": Decimal("8.00"),
                },
                {
                    "order": 3,
                    "min_liters": Decimal("500.00"),
                    "bonus_percent": Decimal("12.00"),
                },
            ],
        )
        # Tier thresholds (min_liters * fuel_price, floored to the nearest
        # 1000): 120,000 / 360,000 / 600,000. An amount of 400,000 clears the
        # first two but not the third, so the 8% tier should apply.
        recharge_request = self._create_pending_request(Decimal("400000.00"))

        response = self.gestor_client.post(
            self._approve_url(recharge_request),
            {"review_comments": "Comprobante verificado"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["applied_tier_percent"], 8.0)
        self.assertEqual(response.data["bonus_amount"], 32000.0)
        self.assertEqual(response.data["total_credited"], 432000.0)
        self.assertEqual(response.data["new_balance"], 432000.0)

        recharge_request.refresh_from_db()
        self.assertEqual(recharge_request.status, BalanceRechargeRequest.STATUS_APPROVED)
        self.assertTrue(recharge_request.is_approved)
        self.assertEqual(recharge_request.reviewed_by, self.gestor)
        self.assertIsNotNone(recharge_request.reviewed_at)
        self.assertEqual(recharge_request.review_comments, "Comprobante verificado")

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("432000"))

        modify_funds = ModifyFunds.objects.get(account=self.account)
        self.assertEqual(modify_funds.amount, Decimal("432000"))
        self.assertEqual(modify_funds.gestor, self.gestor)
        self.assertEqual(modify_funds.payment_method.name, "Transferencia Bancaria")
        self.assertIn("Recarga aprobada.", modify_funds.comments)
        self.assertIn("Bonificación 8.0%", modify_funds.comments)

    def test_admin_approves_bonus_is_truncated_not_rounded(self):
        """
        bonus_amount = (amount * bonus_percent / 100).quantize(Decimal("1"),
        rounding=ROUND_DOWN) - any fractional pesos are dropped entirely, they
        are not rounded to the nearest peso. 1000 @ 33.33% = 333.3, which must
        become 333, not 333 rounded normally (which would still be 333 here)
        nor kept as a fraction.
        """
        self._configure_bonification(
            fuel_price=Decimal("1.00"),
            tiers=[
                {
                    "order": 1,
                    "min_liters": Decimal("1.00"),
                    "bonus_percent": Decimal("33.33"),
                }
            ],
        )
        recharge_request = self._create_pending_request(Decimal("1000.00"))

        response = self.gestor_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["bonus_amount"], 333.0)
        self.assertEqual(response.data["total_credited"], 1333.0)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("1333"))

    def test_admin_approves_without_fuel_price_configured_credits_base_amount_only(self):
        """No fuel_price on AppConfig => the `if fuel_price:` branch never runs."""
        self._configure_bonification(fuel_price=None)
        recharge_request = self._create_pending_request(Decimal("500.00"))

        response = self.gestor_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["applied_tier_percent"])
        self.assertEqual(response.data["bonus_amount"], 0.0)
        self.assertEqual(response.data["total_credited"], 500.0)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("500.00"))

    def test_admin_approves_amount_below_lowest_tier_gets_no_bonus(self):
        self._configure_bonification(
            fuel_price=Decimal("1200.00"),
            tiers=[
                {
                    "order": 1,
                    "min_liters": Decimal("100.00"),
                    "bonus_percent": Decimal("5.00"),
                }
            ],
        )
        # Tier threshold is 120,000; this amount falls short of it.
        recharge_request = self._create_pending_request(Decimal("100000.00"))

        response = self.gestor_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["applied_tier_percent"])
        self.assertEqual(response.data["bonus_amount"], 0.0)
        self.assertEqual(response.data["total_credited"], 100000.0)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("100000.00"))

    # --- reject ------------------------------------------------------------

    def test_admin_rejects_recharge_request_leaves_balance_unchanged(self):
        recharge_request = self._create_pending_request(Decimal("750.00"))

        response = self.gestor_client.post(
            self._reject_url(recharge_request),
            {"review_comments": "Comprobante ilegible"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        recharge_request.refresh_from_db()
        self.assertEqual(recharge_request.status, BalanceRechargeRequest.STATUS_REJECTED)
        self.assertTrue(recharge_request.is_rejected)
        self.assertEqual(recharge_request.reviewed_by, self.gestor)
        self.assertIsNotNone(recharge_request.reviewed_at)
        self.assertEqual(recharge_request.review_comments, "Comprobante ilegible")

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("0.00"))
        self.assertFalse(ModifyFunds.objects.filter(account=self.account).exists())

    # --- permissions ---------------------------------------------------------

    def test_non_admin_cannot_approve_or_reject(self):
        recharge_request = self._create_pending_request(Decimal("600.00"))

        approve_response = self.user_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )
        reject_response = self.user_client.post(
            self._reject_url(recharge_request), {}, format="json"
        )

        self.assertEqual(approve_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(reject_response.status_code, status.HTTP_403_FORBIDDEN)

        recharge_request.refresh_from_db()
        self.assertTrue(recharge_request.is_pending)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("0.00"))

    # --- idempotency / already-processed guard ------------------------------

    def test_cannot_approve_already_approved_request_and_balance_is_not_double_credited(self):
        recharge_request = self._create_pending_request(Decimal("300.00"))

        first_response = self.gestor_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.account.refresh_from_db()
        balance_after_first_approval = self.account.balance
        self.assertEqual(balance_after_first_approval, Decimal("300.00"))

        second_response = self.gestor_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "Solo se pueden aprobar solicitudes pendientes", second_response.data["error"]
        )

        # The critical assertion: balance must not have moved a second time.
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, balance_after_first_approval)
        self.assertEqual(
            ModifyFunds.objects.filter(account=self.account).count(), 1
        )

    def test_cannot_reject_already_processed_request(self):
        recharge_request = self._create_pending_request(Decimal("300.00"))

        first_response = self.gestor_client.post(
            self._reject_url(recharge_request), {}, format="json"
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        reject_again_response = self.gestor_client.post(
            self._reject_url(recharge_request), {}, format="json"
        )
        self.assertEqual(reject_again_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "Solo se pueden rechazar solicitudes pendientes",
            reject_again_response.data["error"],
        )

        approve_after_reject_response = self.gestor_client.post(
            self._approve_url(recharge_request), {}, format="json"
        )
        self.assertEqual(
            approve_after_reject_response.status_code, status.HTTP_400_BAD_REQUEST
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("0.00"))
