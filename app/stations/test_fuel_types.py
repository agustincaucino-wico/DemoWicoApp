"""Tests for FuelType and FuelTypePrice models and API endpoints (Phase 1.A)."""

from decimal import Decimal
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from locations.models import Country, Province, City
from stations.models import FuelType, FuelTypePrice, Station
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
        ft = FuelType.objects.create(name="GNC Test")
        self.assertTrue(ft.is_active)


class StationsTestMixin:
    """Helper para crear estaciones de prueba."""

    def create_station(self, name="Estación Test", is_active=True, **kwargs):
        return Station.objects.create(
            name=name,
            province=self.province,
            city=self.city,
            is_active=is_active,
            **kwargs,
        )

    def setUp(self):
        super().setUp()
        self.country = Country.objects.create(name="Argentina")
        self.province = Province.objects.create(name="Córdoba", country=self.country)
        self.city = City.objects.create(name="Córdoba Capital", province=self.province)


class FuelTypePriceModelTests(StationsTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.station = self.create_station(name="Estación Test")
        self.fuel_type = FuelType.objects.create(name="Nafta Super Test")

    def test_create_fuel_type_price(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("350.50"),
            effective_date=date.today(),
        )
        self.assertIn("Nafta Super Test", str(ftp))
        self.assertIn("Estación Test", str(ftp))

    def test_multiple_prices_same_fuel_type(self):
        """Multiple historical prices for the same fuel type + station."""
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today() - timedelta(days=30),
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("350.00"),
            effective_date=date.today(),
        )
        latest = (
            FuelTypePrice.objects.filter(
                fuel_type=self.fuel_type, station=self.station
            )
            .order_by("-effective_date")
            .first()
        )
        self.assertEqual(latest.price, Decimal("350.00"))

    def test_unique_constraint_station_fueltype_date(self):
        """No se puede repetir (station, fuel_type, effective_date)."""
        today = date.today()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=today,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FuelTypePrice.objects.create(
                    fuel_type=self.fuel_type,
                    station=self.station,
                    price=Decimal("320.00"),
                    effective_date=today,
                )


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
            self.list_url, {"name": "GNC Test", "is_active": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(FuelType.objects.filter(name="GNC Test").exists())

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


class FuelTypePriceAPITests(StationsTestMixin, RoleAssignmentMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.station = self.create_station(name="Estación Test")
        self.other_station = self.create_station(name="Otra Estación")
        self.fuel_type = FuelType.objects.create(name="Nafta Super Test")
        self.other_fuel_type = FuelType.objects.create(name="Diesel Test")

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

        self.list_url = reverse("fuel-type-prices-list")

    def test_create_fuel_type_price(self):
        response = self.client.post(
            self.list_url,
            {
                "fuel_type": self.fuel_type.id,
                "station": self.station.id,
                "price": "350.50",
                "effective_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["fuel_type_name"], "Nafta Super Test")
        self.assertEqual(response.data["station_name"], "Estación Test")

    def test_list_fuel_type_prices(self):
        existing = FuelTypePrice.objects.count()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), existing + 1)

    def test_filter_by_fuel_type(self):
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        FuelTypePrice.objects.create(
            fuel_type=self.other_fuel_type,
            station=self.station,
            price=Decimal("280.00"),
            effective_date=date.today(),
        )
        response = self.client.get(
            self.list_url, {"fuel_type": self.fuel_type.id}
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["fuel_type_name"], "Nafta Super Test")

    def test_filter_by_station(self):
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.other_station,
            price=Decimal("310.00"),
            effective_date=date.today(),
        )
        response = self.client.get(
            self.list_url, {"station": self.station.id}
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["station_name"], "Estación Test")

    def test_update_fuel_type_price(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        url = reverse("fuel-type-prices-detail", args=[ftp.id])
        response = self.client.patch(url, {"price": "320.00"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ftp.refresh_from_db()
        self.assertEqual(ftp.price, Decimal("320.00"))

    def test_delete_fuel_type_price(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        url = reverse("fuel-type-prices-detail", args=[ftp.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FuelTypePrice.objects.filter(id=ftp.id).exists())

    def test_duplicate_station_fueltype_date_returns_400(self):
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        response = self.client.post(
            self.list_url,
            {
                "fuel_type": self.fuel_type.id,
                "station": self.station.id,
                "price": "310.00",
                "effective_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_price_returns_400(self):
        response = self.client.post(
            self.list_url,
            {
                "fuel_type": self.fuel_type.id,
                "station": self.station.id,
                "price": "-10.00",
                "effective_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_price_returns_400(self):
        response = self.client.post(
            self.list_url,
            {
                "fuel_type": self.fuel_type.id,
                "station": self.station.id,
                "price": "0",
                "effective_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_regular_user_can_read(self):
        """Un usuario autenticado común puede leer (GET) los precios."""
        response = self.regular_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_user_cannot_create(self):
        response = self.regular_client.post(
            self.list_url,
            {
                "fuel_type": self.fuel_type.id,
                "station": self.station.id,
                "price": "300.00",
                "effective_date": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_update(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        url = reverse("fuel-type-prices-detail", args=[ftp.id])
        response = self.regular_client.patch(url, {"price": "320.00"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_delete(self):
        ftp = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=date.today(),
        )
        url = reverse("fuel-type-prices-detail", args=[ftp.id])
        response = self.regular_client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_gets_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class FuelTypePriceCurrentEndpointTests(StationsTestMixin, RoleAssignmentMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.station = self.create_station(name="Estación Vigente")
        self.other_station = self.create_station(name="Otra Estación Vigente")
        self.inactive_station = self.create_station(
            name="Estación Inactiva", is_active=False
        )
        self.fuel_type = FuelType.objects.create(name="Nafta Super Vigente")
        self.inactive_fuel_type = FuelType.objects.create(
            name="Combustible Inactivo", is_active=False
        )

        self.user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self.assign_role(self.user, "Gestor")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.current_url = reverse("fuel-type-prices-current")

    def test_returns_most_recent_price_not_future(self):
        today = date.today()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=today - timedelta(days=10),
        )
        current = FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("350.00"),
            effective_date=today,
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("400.00"),
            effective_date=today + timedelta(days=5),
        )

        response = self.client.get(self.current_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], current.id)
        self.assertEqual(response.data[0]["price"], "350.00")

    def test_one_row_per_station_and_fuel_type(self):
        today = date.today()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=today,
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.other_station,
            price=Decimal("310.00"),
            effective_date=today,
        )
        response = self.client.get(self.current_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_filter_by_station(self):
        today = date.today()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=today,
        )
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.other_station,
            price=Decimal("310.00"),
            effective_date=today,
        )
        response = self.client.get(self.current_url, {"station": self.station.id})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["station"], self.station.id)

    def test_excludes_inactive_station(self):
        today = date.today()
        FuelTypePrice.objects.create(
            fuel_type=self.fuel_type,
            station=self.inactive_station,
            price=Decimal("300.00"),
            effective_date=today,
        )
        response = self.client.get(self.current_url)
        self.assertEqual(len(response.data), 0)

    def test_excludes_inactive_fuel_type(self):
        today = date.today()
        FuelTypePrice.objects.create(
            fuel_type=self.inactive_fuel_type,
            station=self.station,
            price=Decimal("300.00"),
            effective_date=today,
        )
        response = self.client.get(self.current_url)
        self.assertEqual(len(response.data), 0)
