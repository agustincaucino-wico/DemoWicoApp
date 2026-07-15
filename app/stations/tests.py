from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from locations.models import Country, Province, City
from stations.models import Station, StationAttendantAssignment
from users.models import CustomUser
from users.test_helpers import RoleAssignmentMixin


class StationAPITests(RoleAssignmentMixin, TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="Testland")
        self.province = Province.objects.create(name="Central", country=self.country)
        self.other_province = Province.objects.create(
            name="North", country=self.country
        )
        self.city = City.objects.create(name="Capital City", province=self.province)
        self.other_city = City.objects.create(
            name="Harbor Town", province=self.other_province
        )

        self.station_alpha = Station.objects.create(
            name="Alpha",
            province=self.province,
            city=self.city,
            street="First",
            street_number="1",
        )
        self.station_beta = Station.objects.create(
            name="Beta",
            province=self.province,
            city=self.city,
            street="Second",
            street_number="2",
        )
        self.station_gamma = Station.objects.create(
            name="Gamma",
            province=self.other_province,
            city=self.other_city,
            street="Third",
            street_number="3",
        )

        self.gestor = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self.assign_role(self.gestor, "Gestor")

        self.auth_client = APIClient()
        self.auth_client.force_authenticate(user=self.gestor)

        self.list_url = reverse("stations-list")

    def test_authentication_required_for_listing(self):
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_filters_by_province_and_city_and_orders_by_name(self):
        response = self.auth_client.get(
            self.list_url, {"province": self.province.id, "city": self.city.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in response.data]
        self.assertEqual(names, ["Alpha", "Beta"])
        self.assertTrue(all(item["province_name"] for item in response.data))
        returned_ids = {item["id"] for item in response.data}
        self.assertSetEqual(returned_ids, {self.station_alpha.id, self.station_beta.id})

    def test_create_station_requires_permissions(self):
        payload = {
            "name": "Delta",
            "province": self.other_province.id,
            "city": self.other_city.id,
            "street": "Fourth",
            "street_number": "4",
        }
        response = self.auth_client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Station.objects.filter(name="Delta", province=self.other_province).exists()
        )

        user_without_perms = CustomUser.objects.create_user(
            email="viewer@example.com", password="pass1234"
        )
        client = APIClient()
        client.force_authenticate(user=user_without_perms)
        response = client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_attendant_assignment_filters_by_station_and_attendant(self):
        attendant_one = CustomUser.objects.create_user(
            email="attendant1@example.com", password="pass1234"
        )
        attendant_two = CustomUser.objects.create_user(
            email="attendant2@example.com", password="pass1234"
        )
        assign_url = reverse("station-attendant-assignments-list")

        assignment_one = StationAttendantAssignment.objects.create(
            attendant=attendant_one,
            station=self.station_alpha,
            start_date=timezone.now().date(),
        )
        StationAttendantAssignment.objects.create(
            attendant=attendant_one,
            station=self.station_gamma,
            start_date=timezone.now().date(),
        )
        StationAttendantAssignment.objects.create(
            attendant=attendant_two,
            station=self.station_alpha,
            start_date=timezone.now().date(),
        )

        # Requires view permission (Gestor has it)
        response = self.auth_client.get(
            assign_url,
            {"station": self.station_alpha.id, "attendant": attendant_one.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data}
        self.assertSetEqual(returned_ids, {assignment_one.id})

        # User without permissions should be forbidden
        client = APIClient()
        user_without_perms = CustomUser.objects.create_user(
            email="viewer2@example.com", password="pass1234"
        )
        client.force_authenticate(user=user_without_perms)
        forbidden_response = client.get(assign_url)
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)
