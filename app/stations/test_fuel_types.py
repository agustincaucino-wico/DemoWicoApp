"""Tests for FuelType and FuelTypePrice models and API endpoints (Phase 1.A)."""

from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Company, Organism
from locations.models import Country, Province, City
from stations.models import FuelType, FuelTypePrice
from users.models import CustomUser
from users.test_helpers import RoleAssignmentMixin


class FuelTypeModelTests(TestCase):
    def test_create_fuel_type(self):
        ft = FuelType.objects.create(name="Nafta Super", is_active=True)
        self.assertEqual(str(ft), "Nafta Super")
        self.assertTrue(ft.is_active)

    def test_fuel_type_unique_name(self):
        FuelType.objects.create(name="Diesel")
        with self.assertRaises(Exception):
            FuelType.objects.create(name="Diesel")

    def test_fuel_type_default_active(self):
        ft = FuelType.objects.create(name="GNC")
        self.assertTrue(ft.is_active)


class FuelTypePriceModelTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="Argentina")
        self.province = Province.objects.create(name="Córdoba", country=self.country)
        self.organism = Organism.objects.get_or_create(
            name="Gobierno de Córdoba",
            defaults={"cuit": "30-12345678-9", "billing_type": "invoice"},
        )[0]
        self.company = Company.objects.create(
            name="Empresa Test", province=self.province, organism=self.organism
        )
        self.fuel_type = FuelType.objects.create(name="Nafta Super Test")

    def test_create_fuel_type_price(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("350.50"),
            effective_date=date.today(),
        )
        self.assertIn("Nafta Super Test", str(ftp))
        self.assertIn("Empresa Test", str(ftp))

    def test_multiple_prices_same_fuel_type(self):
        """Multiple historical prices for the same fuel type + company."""
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("300.00"),
            effective_date=date.today() - timedelta(days=30),
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("350.00"),
            effective_date=date.today(),
        )
        latest = (
            FuelTypePrice.objects.filter(
                fuel_type=self.fuel_type, company=self.company
            )
            .order_by("-effective_date")
            .first()
        )
        self.assertEqual(latest.price, Decimal("350.00"))


class FuelTypeAPITests(RoleAssignmentMixin, TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self.assign_role(self.user, "Gestor")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.regular_user = CustomUser.objects.create_user(
            email="regular@example.com", password="pass1234"
        )
        self.regular_client = APIClient()
        self.regular_client.force_authenticate(user=self.regular_user)

        self.list_url = reverse("fuel-types-list")

    def test_gestor_can_list_fuel_types(self):
        existing = FuelType.objects.count()
        FuelType.objects.create(name="Nafta Super Test")
        FuelType.objects.create(name="Diesel Test")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), existing + 2)

    def test_gestor_can_create_fuel_type(self):
        response = self.client.post(
            self.list_url, {"name": "GNC", "is_active": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(FuelType.objects.filter(name="GNC").exists())

    def test_gestor_can_update_fuel_type(self):
        ft = FuelType.objects.create(name="Nafta Premium")
        url = reverse("fuel-types-detail", args=[ft.id])
        response = self.client.patch(url, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ft.refresh_from_db()
        self.assertFalse(ft.is_active)

    def test_gestor_can_delete_fuel_type(self):
        ft = FuelType.objects.create(name="To Delete")
        url = reverse("fuel-types-detail", args=[ft.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FuelType.objects.filter(id=ft.id).exists())

    def test_regular_user_can_access_fuel_types(self):
        response = self.regular_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_user_cannot_create_fuel_type(self):
        response = self.regular_client.post(
            self.list_url, {"name": "GNC"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FuelTypePriceAPITests(RoleAssignmentMixin, TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="Argentina")
        self.province = Province.objects.create(name="Córdoba", country=self.country)
        self.organism = Organism.objects.get_or_create(
            name="Gobierno de Córdoba",
            defaults={"cuit": "30-12345678-9", "billing_type": "invoice"},
        )[0]
        self.company = Company.objects.create(
            name="Empresa Test", province=self.province, organism=self.organism
        )
        self.other_company = Company.objects.create(
            name="Otra Empresa", province=self.province, organism=self.organism
        )
        self.fuel_type = FuelType.objects.create(name="Nafta Super Test")
        self.other_fuel_type = FuelType.objects.create(name="Diesel Test")

        self.user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self.assign_role(self.user, "Gestor")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.list_url = reverse("fuel-type-prices-list")

    def test_create_fuel_type_price(self):
        response = self.client.post(
            self.list_url,
            {
                "fuel_type": self.fuel_type.id,
                "company": self.company.id,
                "price": "350.50",
                "effective_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["fuel_type_name"], "Nafta Super Test")
        self.assertEqual(response.data["company_name"], "Empresa Test")

    def test_list_fuel_type_prices(self):
        existing = FuelTypePrice.objects.count()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), existing + 1)

    def test_filter_by_fuel_type(self):
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        FuelTypePrice.objects.create(
            fuel_type=self.other_fuel_type,
            company=self.company,
            price=Decimal("280.00"),
            effective_date=date.today(),
        )
        response = self.client.get(
            self.list_url, {"fuel_type": self.fuel_type.id}
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["fuel_type_name"], "Nafta Super Test")

    def test_filter_by_company(self):
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.other_company,
            price=Decimal("310.00"),
            effective_date=date.today(),
        )
        response = self.client.get(
            self.list_url, {"company": self.company.id}
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["company_name"], "Empresa Test")

    def test_update_fuel_type_price(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            company=self.company,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        url = reverse("fuel-type-prices-detail", args=[ftp.id])
        response = self.client.patch(url, {"price": "320.00"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ftp.refresh_from_db()
        self.assertEqual(ftp.price, Decimal("320.00"))

    def test_regular_user_cannot_access(self):
        regular_user = CustomUser.objects.create_user(
            email="regular@example.com", password="pass1234"
        )
        regular_client = APIClient()
        regular_client.force_authenticate(user=regular_user)
        response = regular_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
