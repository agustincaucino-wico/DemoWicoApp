from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from support.models import ErrorReport
from users.roles import ROLES

User = get_user_model()


class ErrorReportPermissionTests(APITestCase):
    """Comprehensive tests for ErrorReport endpoints and permissions."""

    def setUp(self):
        # Regular user (no special permissions)
        self.regular_user = User.objects.create_user(
            email="regular@test.com", password="testpass123"
        )
        # Another regular user
        self.other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        # Gestor user (with role permissions)
        self.gestor_user = User.objects.create_user(
            email="gestor@test.com", password="testpass123"
        )
        self._assign_gestor_role(self.gestor_user)

        # Create error reports for different users
        self.user_report = ErrorReport.objects.create(
            user=self.regular_user,
            category="fuel_load",
            description="Test error report from regular user",
        )
        self.other_report = ErrorReport.objects.create(
            user=self.other_user,
            category="login",
            description="Test error report from other user",
        )

        # Setup clients
        self.anon_client = APIClient()
        self.user_client = APIClient()
        self.user_client.force_authenticate(user=self.regular_user)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other_user)
        self.gestor_client = APIClient()
        self.gestor_client.force_authenticate(user=self.gestor_user)

        self.base_url = "/support/error-reports/"

    def _assign_gestor_role(self, user):
        """Assign Gestor role permissions to a user."""
        group, _ = Group.objects.get_or_create(name="Gestor")
        for perm_codename in ROLES["Gestor"]:
            try:
                perm = Permission.objects.get(codename=perm_codename)
                group.permissions.add(perm)
            except Permission.DoesNotExist:
                pass
        user.groups.add(group)

    # =========================================================================
    # CREATE (POST) - Any authenticated user can create
    # =========================================================================

    def test_create_unauthenticated_denied(self):
        """Unauthenticated users cannot create error reports."""
        payload = {"category": "other", "description": "Anonymous report"}
        response = self.anon_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_authenticated_user_success(self):
        """Any authenticated user can create an error report."""
        payload = {"category": "balance", "description": "Can't see my balance"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["category"], "balance")
        self.assertEqual(response.data["description"], "Can't see my balance")
        self.assertEqual(response.data["status"], "pending")

    def test_create_user_auto_assigned(self):
        """The authenticated user is automatically assigned to the report."""
        payload = {"category": "login", "description": "Login issues"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = ErrorReport.objects.get(id=response.data["id"])
        self.assertEqual(report.user, self.regular_user)

    def test_create_gestor_can_also_create(self):
        """Gestor users can also create error reports."""
        payload = {"category": "transactions", "description": "Gestor report"}
        response = self.gestor_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_all_valid_categories(self):
        """Test creating reports with all valid category choices."""
        categories = ["login", "balance", "fuel_load", "transactions", "other"]
        for cat in categories:
            payload = {"category": cat, "description": f"Testing {cat} category"}
            response = self.user_client.post(self.base_url, payload, format="json")
            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
                f"Failed for category: {cat}",
            )

    def test_create_invalid_category_rejected(self):
        """Creating a report with an invalid category is rejected."""
        payload = {"category": "invalid_category", "description": "Bad category"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_create_missing_category_rejected(self):
        """Creating a report without category is rejected."""
        payload = {"description": "No category provided"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_missing_description_rejected(self):
        """Creating a report without description is rejected."""
        payload = {"category": "other"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_empty_description_rejected(self):
        """Creating a report with empty description is rejected."""
        payload = {"category": "other", "description": ""}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # LIST (GET) - Only Gestor can list
    # =========================================================================

    def test_list_unauthenticated_denied(self):
        """Unauthenticated users cannot list error reports."""
        response = self.anon_client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_regular_user_denied(self):
        """Regular users cannot list error reports."""
        response = self.user_client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_gestor_success(self):
        """Gestor can list all error reports."""
        response = self.gestor_client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)

    def test_list_gestor_sees_all_reports(self):
        """Gestor sees reports from all users."""
        response = self.gestor_client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        report_ids = [r["id"] for r in response.data]
        self.assertIn(self.user_report.id, report_ids)
        self.assertIn(self.other_report.id, report_ids)

    # =========================================================================
    # RETRIEVE (GET detail) - Only Gestor can view details
    # =========================================================================

    def test_retrieve_unauthenticated_denied(self):
        """Unauthenticated users cannot view report details."""
        response = self.anon_client.get(f"{self.base_url}{self.user_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_regular_user_own_report_denied(self):
        """Regular user cannot view even their own report details."""
        response = self.user_client.get(f"{self.base_url}{self.user_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_regular_user_other_report_denied(self):
        """Regular user cannot view other users' report details."""
        response = self.user_client.get(f"{self.base_url}{self.other_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_gestor_any_report_success(self):
        """Gestor can view any error report details."""
        response = self.gestor_client.get(f"{self.base_url}{self.user_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user_report.id)
        self.assertEqual(response.data["category"], "fuel_load")

    def test_retrieve_nonexistent_report_404(self):
        """Requesting a nonexistent report returns 404."""
        response = self.gestor_client.get(f"{self.base_url}99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # UPDATE (PATCH) - Only Gestor can update
    # =========================================================================

    def test_update_unauthenticated_denied(self):
        """Unauthenticated users cannot update reports."""
        payload = {"status": "in_progress"}
        response = self.anon_client.patch(
            f"{self.base_url}{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_regular_user_own_report_denied(self):
        """Regular user cannot update even their own report."""
        payload = {"status": "resolved"}
        response = self.user_client.patch(
            f"{self.base_url}{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_regular_user_other_report_denied(self):
        """Regular user cannot update other users' reports."""
        payload = {"status": "resolved"}
        response = self.user_client.patch(
            f"{self.base_url}{self.other_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_gestor_success(self):
        """Gestor can update any report status."""
        payload = {"status": "in_progress"}
        response = self.gestor_client.patch(
            f"{self.base_url}{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_report.refresh_from_db()
        self.assertEqual(self.user_report.status, "in_progress")

    def test_update_all_valid_statuses(self):
        """Gestor can update to all valid status choices."""
        statuses = ["pending", "in_progress", "resolved", "closed"]
        for stat in statuses:
            payload = {"status": stat}
            response = self.gestor_client.patch(
                f"{self.base_url}{self.user_report.id}/", payload, format="json"
            )
            self.assertEqual(
                response.status_code, status.HTTP_200_OK, f"Failed for status: {stat}"
            )
            self.user_report.refresh_from_db()
            self.assertEqual(self.user_report.status, stat)

    def test_update_invalid_status_rejected(self):
        """Updating with an invalid status is rejected."""
        payload = {"status": "invalid_status"}
        response = self.gestor_client.patch(
            f"{self.base_url}{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_nonexistent_report_404(self):
        """Updating a nonexistent report returns 404."""
        payload = {"status": "resolved"}
        response = self.gestor_client.patch(
            f"{self.base_url}99999/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # DELETE - Only Gestor can delete
    # =========================================================================

    def test_delete_unauthenticated_denied(self):
        """Unauthenticated users cannot delete reports."""
        response = self.anon_client.delete(f"{self.base_url}{self.user_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(ErrorReport.objects.filter(id=self.user_report.id).exists())

    def test_delete_regular_user_own_report_denied(self):
        """Regular user cannot delete even their own report."""
        response = self.user_client.delete(f"{self.base_url}{self.user_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ErrorReport.objects.filter(id=self.user_report.id).exists())

    def test_delete_regular_user_other_report_denied(self):
        """Regular user cannot delete other users' reports."""
        response = self.user_client.delete(f"{self.base_url}{self.other_report.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ErrorReport.objects.filter(id=self.other_report.id).exists())

    def test_delete_gestor_success(self):
        """Gestor can delete any report."""
        report_id = self.other_report.id
        response = self.gestor_client.delete(f"{self.base_url}{report_id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(ErrorReport.objects.filter(id=report_id).exists())

    def test_delete_nonexistent_report_404(self):
        """Deleting a nonexistent report returns 404."""
        response = self.gestor_client.delete(f"{self.base_url}99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # PUT (Full update) - Should be disabled
    # =========================================================================

    def test_put_method_not_allowed(self):
        """PUT method is not allowed (only PATCH for partial updates)."""
        payload = {
            "category": "other",
            "description": "Full update attempt",
            "status": "resolved",
        }
        response = self.gestor_client.put(
            f"{self.base_url}{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # =========================================================================
    # Model behavior tests
    # =========================================================================

    def test_report_default_status_is_pending(self):
        """New reports default to 'pending' status."""
        payload = {"category": "other", "description": "New report"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")

    def test_report_has_timestamps(self):
        """Reports have created_at and updated_at timestamps."""
        payload = {"category": "other", "description": "Timestamp test"}
        response = self.user_client.post(self.base_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("created_at", response.data)
        self.assertIn("updated_at", response.data)
