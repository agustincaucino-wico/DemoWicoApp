import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from users.models import PasswordResetToken, EmailVerificationToken
from users.test_helpers import RoleAssignmentMixin
from utils.email_service import EmailService

User = get_user_model()


class UserViewSetPermissionTests(RoleAssignmentMixin, APITestCase):
    """Test permission handling in UserViewSet."""

    def setUp(self):
        # Reset the cache-backed AnonRateThrottle bucket so accumulated
        # anonymous requests from earlier tests can't throttle the anonymous
        # registration calls here to 429.
        cache.clear()

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
        # Reset the cache-backed AnonRateThrottle bucket so accumulated
        # anonymous requests from earlier tests can't throttle these to 429.
        cache.clear()

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
        # Reset the cache-backed AnonRateThrottle bucket so accumulated
        # anonymous requests from earlier tests can't throttle these to 429.
        cache.clear()

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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetFlowTests(APITestCase):
    """
    End-to-end tests for the unauthenticated password reset flow, hitting the
    real /users/password-reset-{request,verify,confirm}/ endpoints.

    The locmem email backend is forced so send_password_reset_email actually
    succeeds (the test settings otherwise point at a real SMTP host, which
    would make send_email return False and turn every request into a 500).

    Behavior confirmed by reading the real code:
      - The request endpoint returns an identical 200 message whether or not
        the email exists (enumeration defense), rate-limits at
        PasswordResetToken.MAX_REQUESTS_PER_HOUR, and 500s if the email fails.
      - get_valid_token filters used=False AND checks expiry, so a used or
        expired code is rejected as invalid.
      - confirm marks the token used=True, which is what blocks replay.
      - confirm's serializer validates the new password BEFORE the token is
        looked up, so a rejected password does not consume the token.
    """

    REQUEST_URL = "/users/password-reset-request/"
    VERIFY_URL = "/users/password-reset-verify/"
    CONFIRM_URL = "/users/password-reset-confirm/"
    TOKEN_URL = "/api/token/"

    def setUp(self):
        # These endpoints are AllowAny, so DRF's AnonRateThrottle (40/min)
        # applies. It is cache-backed (default LocMemCache), which TestCase's
        # transaction rollback does NOT reset - so the anonymous-request bucket
        # otherwise accumulates across the whole suite and eventually throttles
        # _request_code() to 429, leaving no token and failing these tests
        # order-dependently. Clear the cache so each test starts with a fresh
        # throttle budget. (The app's own DB-based per-user rate limiter is
        # unaffected and still exercised by test_request_is_rate_limited.)
        cache.clear()

        self.email = "reset-user@example.com"
        self.old_password = "ClaveVieja2025!"
        self.user = User.objects.create_user(
            email=self.email, password=self.old_password
        )
        # Login enforces email_verified; set it so the post-reset login
        # assertion actually exercises the credential change.
        self.user.email_verified = True
        self.user.save()
        self.client = APIClient()

    def _request_code(self, email=None):
        return self.client.post(
            self.REQUEST_URL, {"email": email or self.email}, format="json"
        )

    def _latest_code(self):
        return (
            PasswordResetToken.objects.filter(user=self.user, used=False)
            .latest("created_at")
            .token
        )

    # --- request endpoint ---------------------------------------------------

    def test_request_for_nonexistent_email_is_indistinguishable_from_real(self):
        """Enumeration defense: same 200 message, and no token/email produced."""
        ghost = self.client.post(
            self.REQUEST_URL, {"email": "ghost@example.com"}, format="json"
        )
        real = self._request_code()

        self.assertEqual(ghost.status_code, status.HTTP_200_OK)
        self.assertEqual(real.status_code, status.HTTP_200_OK)
        self.assertEqual(ghost.data["message"], real.data["message"])

        # Only the real user ever got a token, and only one email went out.
        self.assertFalse(
            PasswordResetToken.objects.filter(user__isnull=True).exists()
        )
        self.assertEqual(PasswordResetToken.objects.count(), 1)
        self.assertEqual(PasswordResetToken.objects.first().user, self.user)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_is_rate_limited_after_max_requests(self):
        max_requests = PasswordResetToken.MAX_REQUESTS_PER_HOUR
        for _ in range(max_requests):
            self.assertEqual(self._request_code().status_code, status.HTTP_200_OK)

        limited = self._request_code()
        self.assertEqual(limited.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        # The rejected request must not have created another token.
        self.assertEqual(
            PasswordResetToken.objects.filter(user=self.user).count(), max_requests
        )

    def test_request_returns_500_when_email_send_fails(self):
        with patch.object(
            EmailService, "send_password_reset_email", return_value=False
        ):
            response = self._request_code()
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # The token is created before the send is attempted; it simply won't be
        # delivered. Documenting that a failed send still leaves a token behind.
        self.assertEqual(PasswordResetToken.objects.filter(user=self.user).count(), 1)

    # --- verify endpoint ----------------------------------------------------

    def test_verify_rejects_invalid_code(self):
        self._request_code()
        real_code = self._latest_code()
        wrong_code = "999999" if real_code != "999999" else "000000"

        response = self.client.post(
            self.VERIFY_URL,
            {"email": self.email, "code": wrong_code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["valid"])

    def test_verify_rejects_expired_code(self):
        self._request_code()
        token = PasswordResetToken.objects.get(user=self.user)
        expired_at = timezone.now() - timedelta(
            minutes=PasswordResetToken.TOKEN_EXPIRY_MINUTES + 1
        )
        # created_at is auto_now_add, so bypass it with a direct UPDATE.
        PasswordResetToken.objects.filter(id=token.id).update(created_at=expired_at)

        response = self.client.post(
            self.VERIFY_URL,
            {"email": self.email, "code": token.token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["valid"])

    # --- full flow + confirm ------------------------------------------------

    def test_full_reset_flow_then_login_with_new_password(self):
        request_response = self._request_code()
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)

        # Pull the code out of the actual email the user would receive.
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"\b(\d{6})\b", mail.outbox[0].body)
        self.assertIsNotNone(match, "No 6-digit code found in the reset email body")
        code = match.group(1)

        verify_response = self.client.post(
            self.VERIFY_URL, {"email": self.email, "code": code}, format="json"
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.data["valid"])

        new_password = "NuevaClave2026!"
        confirm_response = self.client.post(
            self.CONFIRM_URL,
            {"email": self.email, "code": code, "new_password": new_password},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)

        # New password works at the real token endpoint...
        login_new = self.client.post(
            self.TOKEN_URL,
            {"email": self.email, "password": new_password},
            format="json",
        )
        self.assertEqual(login_new.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_new.data)

        # ...and the old one no longer does.
        login_old = self.client.post(
            self.TOKEN_URL,
            {"email": self.email, "password": self.old_password},
            format="json",
        )
        self.assertEqual(login_old.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_confirm_marks_token_used_and_blocks_replay(self):
        self._request_code()
        code = self._latest_code()
        new_password = "NuevaClave2026!"

        first = self.client.post(
            self.CONFIRM_URL,
            {"email": self.email, "code": code, "new_password": new_password},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        token = PasswordResetToken.objects.get(user=self.user)
        self.assertTrue(token.used)

        # Replaying the same code must fail and must NOT apply the new password.
        replay = self.client.post(
            self.CONFIRM_URL,
            {"email": self.email, "code": code, "new_password": "OtraClave2026!"},
            format="json",
        )
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password("OtraClave2026!"))

    def test_confirm_rejects_invalid_code_and_leaves_password_unchanged(self):
        self._request_code()
        real_code = self._latest_code()
        wrong_code = "999999" if real_code != "999999" else "000000"

        response = self.client.post(
            self.CONFIRM_URL,
            {
                "email": self.email,
                "code": wrong_code,
                "new_password": "NuevaClave2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_confirm_rejects_weak_password_without_consuming_token(self):
        """
        The serializer validates new_password before the token is looked up, so
        a policy-rejected password 400s without burning the code - the user can
        retry with the same code.
        """
        self._request_code()
        code = self._latest_code()

        response = self.client.post(
            self.CONFIRM_URL,
            {"email": self.email, "code": code, "new_password": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        token = PasswordResetToken.objects.get(user=self.user)
        self.assertFalse(token.used)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_requesting_new_code_invalidates_the_previous_token(self):
        """create_for_user marks prior unused tokens used, so only the latest works."""
        self._request_code()
        first_token = PasswordResetToken.objects.get(user=self.user)
        self.assertFalse(first_token.used)

        self._request_code()
        first_token.refresh_from_db()
        self.assertTrue(first_token.used)
        self.assertEqual(
            PasswordResetToken.objects.filter(user=self.user).count(), 2
        )

        # The newest code still verifies.
        latest_code = self._latest_code()
        verify_response = self.client.post(
            self.VERIFY_URL,
            {"email": self.email, "code": latest_code},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailVerificationFlowTests(RoleAssignmentMixin, APITestCase):
    """
    End-to-end tests for the /users/verify_email/, /users/resend_verification/
    and /users/{pk}/mark_email_verified/ endpoints.

    The locmem email backend is forced for the same reason as
    PasswordResetFlowTests: dev settings point at a real SMTP host, which
    would make send_verification_email return False and turn
    resend_verification's happy path into a 500.

    Behavior confirmed by reading the real code:
      - verify_email looks up the token by (token=code, used=False).latest("created_at"),
        so an already-used code is indistinguishable from a wrong one ("Código inválido.").
      - On an expired code, verify_email does NOT set email_verified and does NOT mark
        that token used directly - it calls EmailVerificationToken.create_for_user(user),
        which marks ALL of the user's unused tokens (including the expired one) as used
        as a side effect, and emails a fresh code. email_verified stays False.
      - resend_verification checks email_verified BEFORE generating a token, so a
        verified user gets a 400 with no token created and no email sent.
      - resend_verification generates the token before attempting to send the email,
        so a delivery failure (500) still leaves the token in the database.
      - mark_email_verified requires IsAuthenticated at the action level (401 for
        anonymous) and then manually checks is_superuser OR membership in the
        "Gestor" group (403 otherwise) - either one is sufficient.

    AnonRateThrottle (40/min, default LocMemCache) is keyed by client IP and
    never reset between TestCase classes in the same process, since it lives
    outside the DB transaction rollback. Earlier anonymous-heavy classes in
    this file (or other apps' tests, when the whole suite runs) can exhaust
    the bucket before this class's own anonymous POSTs run. Clear it here so
    these tests are deterministic regardless of run order.
    """

    VERIFY_URL = "/users/verify_email/"
    RESEND_URL = "/users/resend_verification/"

    def setUp(self):
        cache.clear()

    def _mark_expired(self, token):
        expired_at = timezone.now() - timedelta(
            hours=EmailVerificationToken.TOKEN_EXPIRY_HOURS + 1
        )
        # created_at is auto_now_add, so bypass it with a direct UPDATE.
        EmailVerificationToken.objects.filter(id=token.id).update(
            created_at=expired_at
        )

    def _mark_url(self, user):
        return f"/users/{user.id}/mark_email_verified/"

    # --- verify_email ---------------------------------------------------

    def test_verify_email_valid_code_marks_verified_and_consumes_token(self):
        user = User.objects.create_user(
            email="verify-valid@example.com", password="pass1234"
        )
        token = EmailVerificationToken.create_for_user(user)

        response = self.client.post(
            self.VERIFY_URL,
            {"email": user.email, "code": token.token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Email verificado correctamente.")

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        token.refresh_from_db()
        self.assertTrue(token.used)

    def test_verify_email_invalid_code_returns_400(self):
        user = User.objects.create_user(
            email="verify-invalid@example.com", password="pass1234"
        )
        real_token = EmailVerificationToken.create_for_user(user)
        wrong_code = "999999" if real_token.token != "999999" else "000000"

        response = self.client.post(
            self.VERIFY_URL,
            {"email": user.email, "code": wrong_code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Código inválido.")

        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_verify_email_expired_code_regenerates_token_and_sends_new_email(self):
        user = User.objects.create_user(
            email="verify-expired@example.com", password="pass1234"
        )
        old_token = EmailVerificationToken.create_for_user(user)
        self._mark_expired(old_token)

        response = self.client.post(
            self.VERIFY_URL,
            {"email": user.email, "code": old_token.token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expirado", response.data["error"])

        user.refresh_from_db()
        self.assertFalse(user.email_verified)

        # The expired token got swept into "used" as a side effect of
        # generating the replacement, not by verify_email marking it directly.
        old_token.refresh_from_db()
        self.assertTrue(old_token.used)

        fresh_tokens = EmailVerificationToken.objects.filter(
            user=user, used=False
        )
        self.assertEqual(fresh_tokens.count(), 1)
        new_token = fresh_tokens.first()
        self.assertNotEqual(new_token.id, old_token.id)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(new_token.token, mail.outbox[0].body)

    def test_verify_email_replay_of_used_code_rejected(self):
        user = User.objects.create_user(
            email="verify-replay@example.com", password="pass1234"
        )
        token = EmailVerificationToken.create_for_user(user)

        first = self.client.post(
            self.VERIFY_URL,
            {"email": user.email, "code": token.token},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        replay = self.client.post(
            self.VERIFY_URL,
            {"email": user.email, "code": token.token},
            format="json",
        )
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(replay.data["error"], "Código inválido.")

    def test_verify_email_nonexistent_user_returns_400(self):
        response = self.client.post(
            self.VERIFY_URL,
            {"email": "ghost@example.com", "code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Usuario no encontrado.")

    # --- resend_verification ---------------------------------------------

    def test_resend_verification_unverified_user_generates_new_code(self):
        user = User.objects.create_user(
            email="resend-unverified@example.com", password="pass1234"
        )

        response = self.client.post(
            self.RESEND_URL, {"email": user.email}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["message"],
            "Se ha enviado un nuevo código de verificación a tu correo.",
        )

        new_tokens = EmailVerificationToken.objects.filter(
            user=user, used=False
        )
        self.assertEqual(new_tokens.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(new_tokens.first().token, mail.outbox[0].body)

    def test_resend_verification_already_verified_returns_400(self):
        user = User.objects.create_user(
            email="resend-verified@example.com", password="pass1234"
        )
        user.email_verified = True
        user.save()

        response = self.client.post(
            self.RESEND_URL, {"email": user.email}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "El email ya está verificado.")

        self.assertFalse(EmailVerificationToken.objects.filter(user=user).exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_verification_nonexistent_user_returns_400(self):
        response = self.client.post(
            self.RESEND_URL, {"email": "ghost@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Usuario no encontrado.")

    def test_resend_verification_returns_500_when_email_send_fails(self):
        user = User.objects.create_user(
            email="resend-fails@example.com", password="pass1234"
        )

        with patch.object(
            EmailService, "send_verification_email", return_value=False
        ):
            response = self.client.post(
                self.RESEND_URL, {"email": user.email}, format="json"
            )
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # The token is created before the send is attempted; a failed send
        # still leaves it behind.
        self.assertTrue(EmailVerificationToken.objects.filter(user=user).exists())

    # --- mark_email_verified ----------------------------------------------

    def test_mark_email_verified_gestor_succeeds_on_unverified_user(self):
        gestor = User.objects.create_user(
            email="gestor-mark@example.com", password="pass1234"
        )
        self.assign_role(gestor, "Gestor")
        target = User.objects.create_user(
            email="target-mark@example.com", password="pass1234"
        )

        gestor_client = APIClient()
        gestor_client.force_authenticate(user=gestor)
        response = gestor_client.post(self._mark_url(target))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["email_verified"])
        target.refresh_from_db()
        self.assertTrue(target.email_verified)

    def test_mark_email_verified_superuser_without_gestor_group_succeeds(self):
        superuser = User.objects.create_superuser(
            email="superuser-mark@example.com", password="pass1234"
        )
        target = User.objects.create_user(
            email="target-mark-2@example.com", password="pass1234"
        )

        superuser_client = APIClient()
        superuser_client.force_authenticate(user=superuser)
        response = superuser_client.post(self._mark_url(target))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target.refresh_from_db()
        self.assertTrue(target.email_verified)

    def test_mark_email_verified_already_verified_returns_400(self):
        gestor = User.objects.create_user(
            email="gestor-mark-2@example.com", password="pass1234"
        )
        self.assign_role(gestor, "Gestor")
        target = User.objects.create_user(
            email="target-mark-3@example.com", password="pass1234"
        )
        target.email_verified = True
        target.save()

        gestor_client = APIClient()
        gestor_client.force_authenticate(user=gestor)
        response = gestor_client.post(self._mark_url(target))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"], "El email del usuario ya está verificado."
        )

    def test_mark_email_verified_non_admin_returns_403(self):
        regular_user = User.objects.create_user(
            email="regular-mark@example.com", password="pass1234"
        )
        target = User.objects.create_user(
            email="target-mark-4@example.com", password="pass1234"
        )

        regular_client = APIClient()
        regular_client.force_authenticate(user=regular_user)
        response = regular_client.post(self._mark_url(target))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        target.refresh_from_db()
        self.assertFalse(target.email_verified)

    def test_mark_email_verified_unauthenticated_returns_401(self):
        target = User.objects.create_user(
            email="target-mark-5@example.com", password="pass1234"
        )

        response = APIClient().post(self._mark_url(target))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        target.refresh_from_db()
        self.assertFalse(target.email_verified)
