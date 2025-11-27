from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from users.models import CustomUser
from notifications.models import Notification, NotificationPreference


class NotificationModelTests(TestCase):
    """Tests for Notification model methods."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.notification = Notification.objects.create(
            user=self.user,
            title="Test Notification",
            message="This is a test message",
            type="info",
        )

    def test_notification_str_representation(self):
        """Test the string representation of a notification."""
        self.assertEqual(
            str(self.notification), f"Test Notification - {self.user.email}"
        )

    def test_mark_as_read(self):
        """Test marking a notification as read."""
        self.assertFalse(self.notification.is_read)
        self.assertIsNone(self.notification.read_at)

        self.notification.mark_as_read()
        self.notification.refresh_from_db()

        self.assertTrue(self.notification.is_read)
        self.assertIsNotNone(self.notification.read_at)

    def test_mark_as_read_only_updates_once(self):
        """Marking an already read notification shouldn't change read_at."""
        self.notification.mark_as_read()
        first_read_at = self.notification.read_at

        self.notification.mark_as_read()
        self.notification.refresh_from_db()

        self.assertEqual(self.notification.read_at, first_read_at)

    def test_create_notification_helper(self):
        """Test the create_notification class method."""
        notification = Notification.create_notification(
            user=self.user,
            title="Helper Created",
            message="Created via helper",
            notification_type="success",
            action_url="/some/action",
        )
        self.assertEqual(notification.title, "Helper Created")
        self.assertEqual(notification.type, "success")
        self.assertEqual(notification.action_url, "/some/action")
        self.assertFalse(notification.is_read)

    def test_get_unread_count(self):
        """Test getting the unread notification count."""
        # Initially 1 unread (from setUp)
        self.assertEqual(Notification.get_unread_count(self.user), 1)

        # Create another unread
        Notification.objects.create(
            user=self.user, title="Another", message="Another message"
        )
        self.assertEqual(Notification.get_unread_count(self.user), 2)

        # Mark one as read
        self.notification.mark_as_read()
        self.assertEqual(Notification.get_unread_count(self.user), 1)


class NotificationPreferenceModelTests(TestCase):
    """Tests for NotificationPreference model."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="pref@example.com", password="testpass123"
        )
        # Preferences are auto-created by user manager
        self.pref = NotificationPreference.objects.get(user=self.user)

    def test_preference_str_representation(self):
        """Test the string representation of preferences."""
        self.assertEqual(str(self.pref), f"Preferencias de {self.user.email}")

    def test_default_preferences(self):
        """Test that default preferences are enabled."""
        self.assertTrue(self.pref.push_enabled)
        self.assertTrue(self.pref.email_enabled)
        self.assertTrue(self.pref.fuel_load_notifications)
        self.assertTrue(self.pref.account_notifications)
        self.assertTrue(self.pref.balance_notifications)
        self.assertTrue(self.pref.system_notifications)


class NotificationAPITests(TestCase):
    """Tests for Notification API endpoints."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="api@example.com", password="testpass123"
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@example.com", password="testpass123"
        )

        # Create notifications for the user
        self.notification1 = Notification.objects.create(
            user=self.user,
            title="First Notification",
            message="First message",
            type="info",
        )
        self.notification2 = Notification.objects.create(
            user=self.user,
            title="Second Notification",
            message="Second message",
            type="success",
        )
        # Create notification for other user
        self.other_notification = Notification.objects.create(
            user=self.other_user,
            title="Other User Notification",
            message="Other message",
            type="warning",
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.anon_client = APIClient()

    def test_unauthenticated_cannot_list_notifications(self):
        """Unauthenticated users cannot access notifications."""
        response = self.anon_client.get("/notifications/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_list_own_notifications(self):
        """User can list their own notifications."""
        response = self.client.get("/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see their own notifications
        self.assertEqual(response.data["count"], 2)
        self.assertIn("unread_count", response.data)

    def test_user_cannot_see_other_users_notifications(self):
        """User cannot see other users' notifications."""
        response = self.client.get("/notifications/")
        notification_ids = [n["id"] for n in response.data["results"]]
        self.assertNotIn(self.other_notification.id, notification_ids)

    def test_filter_by_read_status(self):
        """Test filtering notifications by read status."""
        # Mark one as read
        self.notification1.mark_as_read()

        # Filter unread
        response = self.client.get("/notifications/?is_read=false")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        # Filter read
        response = self.client.get("/notifications/?is_read=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_type(self):
        """Test filtering notifications by type."""
        response = self.client.get("/notifications/?type=success")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["type"], "success")

    def test_retrieve_marks_as_read(self):
        """Retrieving a notification marks it as read."""
        self.assertFalse(self.notification1.is_read)

        response = self.client.get(f"/notifications/{self.notification1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.notification1.refresh_from_db()
        self.assertTrue(self.notification1.is_read)

    def test_user_cannot_retrieve_others_notification(self):
        """User cannot retrieve another user's notification."""
        response = self.client.get(f"/notifications/{self.other_notification.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_all_read(self):
        """Test marking all notifications as read."""
        self.assertEqual(Notification.get_unread_count(self.user), 2)

        response = self.client.post("/notifications/mark_all_read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 2)

        self.assertEqual(Notification.get_unread_count(self.user), 0)

    def test_mark_specific_as_read(self):
        """Test marking specific notifications as read."""
        response = self.client.post(
            "/notifications/mark_as_read/",
            {"notification_ids": [self.notification1.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 1)

        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        self.assertTrue(self.notification1.is_read)
        self.assertFalse(self.notification2.is_read)

    def test_delete_all_read(self):
        """Test deleting all read notifications."""
        # Mark all as read first
        self.notification1.mark_as_read()
        self.notification2.mark_as_read()

        response = self.client.delete("/notifications/delete_all_read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 2)

        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

    def test_unread_count_endpoint(self):
        """Test getting unread count."""
        response = self.client.get("/notifications/unread_count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)

    def test_delete_single_notification(self):
        """Test deleting a single notification."""
        response = self.client.delete(f"/notifications/{self.notification1.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(id=self.notification1.id).exists())

    def test_user_cannot_delete_others_notification(self):
        """User cannot delete another user's notification."""
        response = self.client.delete(f"/notifications/{self.other_notification.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Notification should still exist
        self.assertTrue(
            Notification.objects.filter(id=self.other_notification.id).exists()
        )


class NotificationPreferenceAPITests(TestCase):
    """Tests for NotificationPreference API endpoints."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="prefapi@example.com", password="testpass123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.anon_client = APIClient()

    def test_unauthenticated_cannot_access_preferences(self):
        """Unauthenticated users cannot access preferences."""
        response = self.anon_client.get("/notifications/preferences/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_preferences_exist_after_user_creation(self):
        """Preferences are auto-created when user is created."""
        # Preferences should already exist (created by user manager)
        self.assertTrue(NotificationPreference.objects.filter(user=self.user).exists())

        response = self.client.get("/notifications/preferences/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_preferences(self):
        """Test updating notification preferences."""
        response = self.client.patch(
            "/notifications/preferences/update_preferences/",
            {"push_enabled": False, "email_enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pref = NotificationPreference.objects.get(user=self.user)
        self.assertFalse(pref.push_enabled)
        self.assertFalse(pref.email_enabled)

    def test_partial_update_preferences(self):
        """Test partial update of preferences."""
        response = self.client.patch(
            "/notifications/preferences/update_preferences/",
            {"fuel_load_notifications": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pref = NotificationPreference.objects.get(user=self.user)
        self.assertFalse(pref.fuel_load_notifications)
        # Others should remain default
        self.assertTrue(pref.push_enabled)
        self.assertTrue(pref.email_enabled)
