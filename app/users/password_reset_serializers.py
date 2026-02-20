"""
Serializers for password reset functionality.
"""

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for requesting a password reset code."""

    email = serializers.EmailField(
        required=True,
        help_text="Email address associated with the account.",
    )

    def validate_email(self, value):
        """Normalize email to lowercase."""
        return value.lower().strip()


class PasswordResetVerifySerializer(serializers.Serializer):
    """Serializer for verifying a password reset code without changing password."""

    email = serializers.EmailField(
        required=True,
        help_text="Email address associated with the account.",
    )
    code = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="6-digit reset code received via email.",
    )

    def validate_email(self, value):
        """Normalize email to lowercase."""
        return value.lower().strip()

    def validate_code(self, value):
        """Ensure code contains only digits."""
        if not value.isdigit():
            raise serializers.ValidationError("El código debe contener solo números.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming password reset with code and new password."""

    email = serializers.EmailField(
        required=True,
        help_text="Email address associated with the account.",
    )
    code = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="6-digit reset code received via email.",
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        help_text="New password (minimum 8 characters).",
    )

    def validate_email(self, value):
        """Normalize email to lowercase."""
        return value.lower().strip()

    def validate_code(self, value):
        """Ensure code contains only digits."""
        if not value.isdigit():
            raise serializers.ValidationError("El código debe contener solo números.")
        return value

    def validate_new_password(self, value):
        """Validate password using Django's password validators."""
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
