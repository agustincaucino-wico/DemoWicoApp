from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from support.models import ErrorReport

User = get_user_model()


class ErrorReportPermissionTests(APITestCase):
    """Test permission handling for ErrorReport endpoints."""

    def setUp(self):
        # Regular user (non-staff)
        self.regular_user = User.objects.create_user(
            email="regular@test.com", password="testpass123"
        )
        # Another regular user
        self.other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        # Staff/Manager user
        self.staff_user = User.objects.create_user(
            email="staff@test.com", password="testpass123", is_staff=True
        )

        # Create error reports
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
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff_user)

    def test_unauthenticated_cannot_create_report(self):
        """Unauthenticated users cannot create error reports."""
        payload = {"category": "other", "description": "Anonymous report"}
        response = self.anon_client.post(
            "/support/error-reports/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_create_report(self):
        """Authenticated users can create error reports."""
        payload = {"category": "balance", "description": "Can't see my balance"}
        response = self.user_client.post(
            "/support/error-reports/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["category"], "balance")

    def test_regular_user_cannot_list_reports(self):
        """Regular users cannot list all error reports."""
        response = self.user_client.get("/support/error-reports/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_list_all_reports(self):
        """Staff users can list all error reports."""
        response = self.staff_client.get("/support/error-reports/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see all reports
        self.assertGreaterEqual(len(response.data), 2)

    def test_regular_user_cannot_view_report_detail(self):
        """Regular users cannot view report details (even their own via this permission)."""
        response = self.user_client.get(
            f"/support/error-reports/{self.user_report.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_view_any_report_detail(self):
        """Staff can view any error report detail."""
        response = self.staff_client.get(
            f"/support/error-reports/{self.user_report.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user_report.id)

    def test_staff_can_update_report_status(self):
        """Staff can update report status."""
        payload = {"status": "in_progress"}
        response = self.staff_client.patch(
            f"/support/error-reports/{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_report.refresh_from_db()
        self.assertEqual(self.user_report.status, "in_progress")

    def test_regular_user_cannot_update_report(self):
        """Regular users cannot update reports."""
        payload = {"status": "resolved"}
        response = self.user_client.patch(
            f"/support/error-reports/{self.user_report.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_delete_report(self):
        """Staff can delete any report."""
        response = self.staff_client.delete(
            f"/support/error-reports/{self.other_report.id}/"
        )
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]
        )
        self.assertFalse(ErrorReport.objects.filter(id=self.other_report.id).exists())
