from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from users.test_helpers import RoleAssignmentMixin

User = get_user_model()


class UserViewSetPermissionTests(RoleAssignmentMixin, APITestCase):
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
        self.assign_role(self.user_with_perms, "Gestor")

        # Setup clients
        self.anon_client = APIClient()
        self.no_perm_client = APIClient()
        self.no_perm_client.force_authenticate(user=self.user_without_perms)
        self.perm_client = APIClient()
        self.perm_client.force_authenticate(user=self.user_with_perms)

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
            "dni": "12345678",
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

    def test_cannot_create_superuser_via_api(self):
        """Cannot create a superuser via the API endpoint."""
        payload = {
            "email": "hacker@test.com",
            "password": "securepass123",
            "dni": "87654321",
            "is_superuser": True,
            "is_staff": True,
        }
        response = self.anon_client.post("/users/", payload, format="json")
        # Should succeed but not create a superuser
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="hacker@test.com")
        # Verify user is NOT a superuser or staff
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_cannot_escalate_to_superuser_via_update(self):
        """Cannot escalate privileges to superuser via update."""
        payload = {
            "is_superuser": True,
            "is_staff": True,
        }
        response = self.no_perm_client.patch(
            f"/users/{self.user_without_perms.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_without_perms.refresh_from_db()
        # Verify user is still NOT a superuser or staff
        self.assertFalse(self.user_without_perms.is_superuser)
        self.assertFalse(self.user_without_perms.is_staff)


class LoginFlowTests(APITestCase):
    """
    Real login flow tests hitting the actual /api/token/ endpoint (no
    force_authenticate). Covers credential validation plus the two extra
    preconditions enforced by CustomTokenObtainPairSerializer/ModelBackend:
    email_verified and is_active.
    """

    TOKEN_URL = "/api/token/"

    def setUp(self):
        self.password = "correct-horse-battery-staple"
        self.user = User.objects.create_user(
            email="login-test@example.com", password=self.password
        )
        # create_user() does not verify the email or activate anything beyond
        # the model default; login requires email_verified explicitly.
        self.user.email_verified = True
        self.user.save()
        self.client = APIClient()

    def test_login_with_valid_credentials_returns_tokens(self):
        response = self.client.post(
            self.TOKEN_URL,
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            self.TOKEN_URL,
            {"email": self.user.email, "password": "not-the-password"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_login_with_nonexistent_email_fails(self):
        response = self.client.post(
            self.TOKEN_URL,
            {"email": "nobody-here@example.com", "password": "whatever"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_login_fails_for_unverified_email(self):
        """CustomTokenObtainPairSerializer rejects login until email_verified=True."""
        self.user.email_verified = False
        self.user.save()

        response = self.client.post(
            self.TOKEN_URL,
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        # The serializer raises this as a ValidationError (not
        # AuthenticationFailed), so it surfaces as 400, not 401.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)
        # DRF wraps each dict value of a raised ValidationError in a list of
        # ErrorDetail; unwrap before comparing.
        self.assertEqual(response.data["status"][0], "unverified")

    def test_login_fails_for_inactive_user(self):
        """
        is_active=False is enforced by Django's ModelBackend before our
        serializer even reaches the email_verified check, so it looks
        identical to a wrong-password failure (401, generic message) rather
        than surfacing as a distinct error.
        """
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            self.TOKEN_URL,
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_access_token_from_login_authenticates_subsequent_request(self):
        """The access token returned by /api/token/ must work as real bearer auth."""
        login_response = self.client.post(
            self.TOKEN_URL,
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        access_token = login_response.data["access"]

        authenticated_client = APIClient()
        authenticated_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = authenticated_client.get("/users/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_access_token_missing_bearer_prefix_is_rejected(self):
        """A raw token without the 'Bearer ' scheme must not authenticate."""
        login_response = self.client.post(
            self.TOKEN_URL,
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        access_token = login_response.data["access"]

        authenticated_client = APIClient()
        authenticated_client.credentials(HTTP_AUTHORIZATION=access_token)
        response = authenticated_client.get("/users/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DevUserLoginViewTests(APITestCase):
    """
    DevUserLoginView (/users/dev/login/) mints a JWT via RefreshToken.for_user()
    with no password, is_active, or email_verified check at all - its only
    protection is the settings.DEBUG gate. These tests pin down both sides of
    that behavior: the endpoint must be a dead 404 under the settings the test
    suite (and presumably production) actually run with, and must genuinely
    work as designed when DEBUG=True, since that's the whole point of it
    existing.
    """

    DEV_LOGIN_URL = "/users/dev/login/"

    def setUp(self):
        self.user = User.objects.create_user(
            email="dev-login-target@example.com", password="whatever-not-checked"
        )
        self.client = APIClient()

    def test_dev_login_returns_404_when_debug_false_regardless_of_payload(self):
        """
        The test suite runs under myapp.settings.dev, which sets DEBUG=False.
        No payload - valid or not - should ever reach the token-minting code.
        """
        for payload in (
            {},
            {"email": self.user.email},
            {"user_id": self.user.id},
            {"email": "nobody-here@example.com"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    self.DEV_LOGIN_URL, payload, format="json"
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertNotIn("access", response.data)
                self.assertNotIn("refresh", response.data)

    @override_settings(DEBUG=True)
    def test_dev_login_issues_valid_token_when_debug_true(self):
        """
        With DEBUG=True (e.g. a developer's local settings), the endpoint
        works exactly as designed: no password required, mints a real token
        for the requested user by email.
        """
        response = self.client.post(
            self.DEV_LOGIN_URL, {"email": self.user.email}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])
        self.assertEqual(response.data["user"]["email"], self.user.email)

        # Confirm it's not a token-shaped placeholder - it actually authenticates.
        authenticated_client = APIClient()
        authenticated_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )
        me_response = authenticated_client.get("/users/me/")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], self.user.email)
