from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from users.models import CustomUser
from .models import Country, Province, City, Address


class LocationsTestCase(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="Testland")
        self.another_country = Country.objects.create(name="Sampleland")

        self.province = Province.objects.create(
            country=self.country, name="Central Province"
        )
        self.other_province = Province.objects.create(
            country=self.country, name="Coast Province"
        )

        self.city = City.objects.create(name="Capitol City", province=self.province)
        self.other_city = City.objects.create(
            name="Harbor City", province=self.other_province
        )

        self.address = Address.objects.create(
            street="Main St", number=10, floor=2, apartment="B", city=self.city
        )
        self.other_address = Address.objects.create(
            street="Second St", number=20, city=self.other_city
        )

        self.admin_user = CustomUser.objects.create_superuser(
            email="admin@example.com", password="pass1234"
        )
        self.regular_user = CustomUser.objects.create_user(
            email="user@example.com", password="pass1234"
        )

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin_user)

        self.user_client = APIClient()
        self.user_client.force_authenticate(user=self.regular_user)

        self.anon_client = APIClient()

    def test_model_str_representations(self):
        self.assertEqual(str(self.country), "Testland")
        self.assertEqual(str(self.province), "Central Province (Testland)")
        self.assertEqual(str(self.city), "Capitol City, Central Province")

        self.assertEqual(str(self.address), "Main St 10, Flr 2, Apt B, Capitol City")
        self.assertEqual(str(self.other_address), "Second St 20, Harbor City")

    def test_public_can_list_countries(self):
        response = self.anon_client.get("/locations/countries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        country_names = {country["name"] for country in response.data}
        self.assertTrue({"Testland", "Sampleland"}.issubset(country_names))

    def test_public_can_list_provinces(self):
        response = self.anon_client.get("/locations/provinces/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        province_names = {province["name"] for province in response.data}
        self.assertTrue({"Central Province", "Coast Province"}.issubset(province_names))

    def test_public_can_list_cities(self):
        response = self.anon_client.get("/locations/cities/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        city_names = {city["name"] for city in response.data}
        self.assertTrue({"Capitol City", "Harbor City"}.issubset(city_names))

    def test_city_filter_by_province(self):
        response = self.anon_client.get(
            f"/locations/cities/?province_id={self.province.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        city_ids = {city["id"] for city in response.data}
        self.assertEqual(city_ids, {self.city.id})

    def test_city_creation_rejects_unknown_province(self):
        payload = {"name": "Ghost City", "province": 9999}
        response = self.admin_client.post("/locations/cities/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("province", response.data)

    def test_address_requires_admin_permissions(self):
        list_response = self.user_client.get("/locations/addresses/")
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)

        create_response = self.user_client.post(
            "/locations/addresses/",
            {"street": "Blocked", "number": 1, "city": self.city.id},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_address_and_filter_by_city(self):
        payload = {"street": "Third Ave", "number": 5, "city": self.city.id}
        response = self.admin_client.post(
            "/locations/addresses/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.admin_client.get(
            f"/locations/addresses/?city_id={self.city.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        returned_cities = {address["city"] for address in response.data}
        self.assertEqual(returned_cities, {self.city.id})

    def test_address_number_must_be_positive(self):
        payload = {"street": "Error St", "number": 0, "city": self.city.id}
        response = self.admin_client.post(
            "/locations/addresses/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("number", response.data)
        self.assertIn("positive", str(response.data["number"]).lower())
