"""Tests for Organism model and API endpoints (Phase 1.A)."""

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Organism
from users.models import CustomUser
from users.roles import ROLES


class OrganismModelTests(TestCase):
    def test_create_organism(self):
        org = Organism.objects.create(
            name="Gobierno de Córdoba",
            cuit="30-12345678-9",
            billing_type="invoice",
        )
        self.assertEqual(str(org), "Gobierno de Córdoba")
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


class OrganismAPITests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="gestor@example.com", password="pass1234"
        )
        self._assign_role(self.user, "Gestor")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.regular_user = CustomUser.objects.create_user(
            email="regular@example.com", password="pass1234"
        )
        self.regular_client = APIClient()
        self.regular_client.force_authenticate(user=self.regular_user)

        self.list_url = reverse("organism-list")

    def _assign_role(self, user, role_name):
        group, _ = Group.objects.get_or_create(name=role_name)
        permissions = Permission.objects.filter(codename__in=ROLES.get(role_name, []))
        group.permissions.set(permissions)
        user.groups.add(group)

    def test_gestor_can_list_organisms(self):
        Organism.objects.create(
            name="Org A", cuit="30-11111111-1", billing_type="invoice"
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_gestor_can_create_organism(self):
        response = self.client.post(
            self.list_url,
            {
                "name": "Gobierno de Córdoba",
                "cuit": "30-12345678-9",
                "billing_type": "invoice",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Organism.objects.filter(name="Gobierno de Córdoba").exists())

    def test_gestor_can_update_organism(self):
        org = Organism.objects.create(
            name="Original", cuit="30-11111111-1", billing_type="invoice"
        )
        url = reverse("organism-detail", args=[org.id])
        response = self.client.patch(url, {"billing_type": "prepaid"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        org.refresh_from_db()
        self.assertEqual(org.billing_type, "prepaid")

    def test_gestor_can_delete_organism(self):
        org = Organism.objects.create(
            name="To Delete", cuit="30-11111111-1", billing_type="invoice"
        )
        url = reverse("organism-detail", args=[org.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Organism.objects.filter(id=org.id).exists())

    def test_regular_user_cannot_access(self):
        response = self.regular_client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_create(self):
        response = self.regular_client.post(
            self.list_url,
            {"name": "Hack", "cuit": "30-99999999-9", "billing_type": "invoice"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
