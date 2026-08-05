import random
import string
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from users.managers import CustomUserManager
from django.utils import timezone
from datetime import timedelta


class PasswordResetToken(models.Model):
    """
    Token for password reset functionality.
    Uses a 6-digit numeric code for mobile-friendly UX.
    Implements rate limiting to prevent abuse.
    """

    user = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    failed_attempts = models.PositiveIntegerField(default=0)

    # Rate limiting
    TOKEN_EXPIRY_MINUTES = 15
    # 30 requests/hour in dev, 3 in production
    MAX_REQUESTS_PER_HOUR = 30 if settings.DEBUG else 3
    # Wrong guesses tolerated on a single token before it's locked out,
    # regardless of DEBUG - unlike MAX_REQUESTS_PER_HOUR this isn't about
    # dev-testing friction, it's a fixed anti-brute-force cap. 5 wrong
    # guesses against a 6-digit code (1,000,000 possible values) keeps the
    # odds of a successful blind guess within the token's lifetime
    # negligible (well under 0.001%) while leaving enough room for a
    # legitimate user to mistype the code a couple of times.
    MAX_VERIFY_ATTEMPTS = 5

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Password reset token for {self.user.email}"

    @classmethod
    def generate_token(cls):
        """Generate a 6-digit numeric code."""
        return "".join(random.choices(string.digits, k=6))

    def is_expired(self):
        """Check if token has expired (15 minutes)."""
        expiry_time = self.created_at + timedelta(minutes=self.TOKEN_EXPIRY_MINUTES)
        return timezone.now() > expiry_time

    @classmethod
    def is_rate_limited(cls, user):
        """
        Check if user has exceeded rate limit (3 requests per hour).
        Returns True if rate limited, False otherwise.
        """
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_tokens = cls.objects.filter(
            user=user,
            created_at__gte=one_hour_ago,
        ).count()
        return recent_tokens >= cls.MAX_REQUESTS_PER_HOUR

    @classmethod
    def create_for_user(cls, user):
        """
        Create a new password reset token for user.
        Invalidates any existing unused tokens.
        """
        # Mark existing unused tokens as used
        cls.objects.filter(user=user, used=False).update(used=True)

        # Create new token
        return cls.objects.create(
            user=user,
            token=cls.generate_token(),
        )

    @classmethod
    def get_valid_token(cls, email, token_code):
        """
        Get a valid (not expired, not used, not locked out) token for the
        given email and code. Returns the token if token_code is correct,
        None otherwise - covering "no pending token", "expired", "locked
        out from too many wrong guesses" and "wrong code" alike, so callers
        can't tell them apart (same as before this method tracked attempts).

        Looked up by (email, used=False) rather than including token_code in
        the query: create_for_user() guarantees at most one unused token per
        user, and a wrong guess needs to land on that same row to have its
        failed_attempts counted - matching on the code up front would never
        find a row for a wrong guess to increment.
        """
        try:
            token = cls.objects.select_related("user").get(
                user__email__iexact=email,
                used=False,
            )
        except cls.DoesNotExist:
            return None

        if token.is_expired():
            return None

        if token.failed_attempts >= cls.MAX_VERIFY_ATTEMPTS:
            return None

        if token.token != token_code:
            token.failed_attempts += 1
            token.save(update_fields=["failed_attempts"])
            return None

        return token


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        unique=True,
        blank=False,
        null=False,
        error_messages={"unique": "El correo electrónico ya se encuentra registrado."},
    )
    dni = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        error_messages={"unique": "El DNI ya se encuentra registrado."},
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_joined = models.DateTimeField(default=timezone.now)
    id_province = models.ForeignKey(
        "locations.Province", on_delete=models.SET_NULL, null=True, blank=True
    )
    id_city = models.ForeignKey(
        "locations.City", on_delete=models.SET_NULL, null=True, blank=True
    )
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    gender = models.CharField(
        max_length=10,
        choices=[
            ("M", "Masculino"),
            ("F", "Femenino"),
            ("X", "No binario"),
        ],  # TODO borrar luego de la migracion
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_authorized_holder = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []  # Only email is required for creating superuser

    objects = CustomUserManager()

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.email

    email_verified = models.BooleanField(default=False)


class EmailVerificationToken(models.Model):
    """
    Token for email verification.
    Uses a 6-digit numeric code.
    """
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="verification_tokens",
    )
    token = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    # Token expires in 24 hours
    TOKEN_EXPIRY_HOURS = 24

    def __str__(self):
        return f"Verification token for {self.user.email}"

    @classmethod
    def generate_token(cls):
        """Generate a 6-digit numeric code."""
        return "".join(random.choices(string.digits, k=6))

    def is_expired(self):
        """Check if token has expired."""
        expiry_time = self.created_at + timedelta(hours=self.TOKEN_EXPIRY_HOURS)
        return timezone.now() > expiry_time

    @classmethod
    def create_for_user(cls, user):
        """Create a new verification token for user."""
        # Invalidate existing tokens
        cls.objects.filter(user=user, used=False).update(used=True)

        return cls.objects.create(
            user=user,
            token=cls.generate_token(),
        )

