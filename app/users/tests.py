from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from users.roles import ROLES

User = get_user_model()


class UserViewSetPermissionTests(APITestCase):
    """Test permission handling in UserViewSet."""

    def setUp(self):
        # Create test users
        self.user_without_perms = User.objects.create_user(
            email="noperm@test.com", password="testpass123"
        )
        self.user_with_perms = User.objects.create_user(
            email="hasperm@test.com", password="testpass123"
        )
        self.target_user = User.objects.create_user(
            email="target@test.com", password="testpass123"
        )

        # Assign Gestor permissions to user_with_perms
        self._assign_gestor_role(self.user_with_perms)

        # Setup clients
        self.anon_client = APIClient()
        self.no_perm_client = APIClient()
        self.no_perm_client.force_authenticate(user=self.user_without_perms)
        self.perm_client = APIClient()
        self.perm_client.force_authenticate(user=self.user_with_perms)

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

    def test_unauthenticated_cannot_list_users(self):
        """Unauthenticated requests should be denied."""
        response = self.anon_client.get("/users/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_permission_cannot_list_users(self):
        """User without view_customuser permission cannot list users."""
        response = self.no_perm_client.get("/users/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_with_permission_can_list_users(self):
        """User with view_customuser permission can list users."""
        response = self.perm_client.get("/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_can_access_own_profile(self):
        """User can access their own profile."""
        response = self.no_perm_client.get(f"/users/{self.user_without_perms.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "noperm@test.com")

    def test_user_cannot_access_other_profile_without_permission(self):
        """User without permission cannot access another user's profile."""
        response = self.no_perm_client.get(f"/users/{self.target_user.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_with_permission_can_access_any_profile(self):
        """User with view_customuser permission can access any profile."""
        response = self.perm_client.get(f"/users/{self.target_user.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "target@test.com")

    def test_anyone_can_create_user(self):
        """Anyone can create a new user (registration)."""
        payload = {
            "email": "newuser@test.com",
            "password": "securepass123",
        }
        response = self.anon_client.post("/users/", payload, format="json")
        # Should succeed (201 Created)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="newuser@test.com").exists())

    def test_user_can_update_own_profile(self):
        """User can update their own profile."""
        payload = {"first_name": "Updated"}
        response = self.no_perm_client.patch(
            f"/users/{self.user_without_perms.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_without_perms.refresh_from_db()
        self.assertEqual(self.user_without_perms.first_name, "Updated")

    def test_user_cannot_update_other_profile_without_permission(self):
        """User without permission cannot update another user's profile."""
        payload = {"first_name": "Hacked"}
        response = self.no_perm_client.patch(
            f"/users/{self.target_user.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_me_endpoint_returns_current_user(self):
        """The /users/me/ endpoint returns the authenticated user."""
        response = self.no_perm_client.get("/users/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "noperm@test.com")

    def test_me_endpoint_requires_authentication(self):
        """The /users/me/ endpoint requires authentication."""
        response = self.anon_client.get("/users/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
