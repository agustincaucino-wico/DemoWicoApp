"""
Views for password reset functionality.
"""

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

from users.models import CustomUser, PasswordResetToken
from users.password_reset_serializers import (
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    PasswordResetConfirmSerializer,
)
from utils.email_service import EmailService

logger = logging.getLogger(__name__)


class PasswordResetRequestView(APIView):
    """
    Request a password reset code.

    Sends a 6-digit code to the user's email if the account exists.
    Implements rate limiting (3 requests per hour per user).

    For security, always returns success even if email doesn't exist
    to prevent email enumeration attacks.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            429: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        summary="Request Password Reset",
        description="Sends a 6-digit code to the user's email if the account exists.",
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        # Always return success message (prevent email enumeration)
        success_message = (
            "Si el correo electrónico está registrado, "
            "recibirás un código de recuperación."
        )

        try:
            user = CustomUser.objects.get(email__iexact=email)
        except CustomUser.DoesNotExist:
            logger.info(f"Password reset requested for non-existent email: {email}")
            return Response(
                {"message": success_message},
                status=status.HTTP_200_OK,
            )

        # Check rate limiting
        if PasswordResetToken.is_rate_limited(user):
            logger.warning(f"Rate limit exceeded for password reset: {email}")
            return Response(
                {
                    "error": "Has solicitado demasiados códigos de recuperación. "
                    "Por favor, espera una hora antes de intentar nuevamente."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Create token
        token = PasswordResetToken.create_for_user(user)

        # Send email
        email_service = EmailService()
        email_sent = email_service.send_password_reset_email(
            to_email=user.email,
            user_name=user.get_full_name() or user.email,
            reset_code=token.token,
        )

        if not email_sent:
            logger.error(f"Failed to send password reset email to: {email}")
            return Response(
                {"error": "Error al enviar el correo. Por favor, intenta nuevamente."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(f"Password reset code sent to: {email}")
        return Response(
            {"message": success_message},
            status=status.HTTP_200_OK,
        )


class PasswordResetVerifyView(APIView):
    """
    Verify a password reset code without changing the password.

    This endpoint checks if the code is valid and not expired.
    Use this before showing the password change form.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetVerifySerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
        summary="Verify Password Reset Code",
        description="Verify a password reset code without changing the password.",
    )
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        # Get valid token
        token = PasswordResetToken.get_valid_token(email, code)

        if not token:
            logger.warning(f"Invalid or expired reset code verification for: {email}")
            return Response(
                {"valid": False, "error": "Código inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(f"Password reset code verified for: {email}")
        return Response(
            {"valid": True, "message": "Código verificado correctamente."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    Confirm password reset with code and set new password.

    Validates the 6-digit code and updates the user's password.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
        },
        summary="Confirm Password Reset",
        description="Confirm password reset with code and set new password.",
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]

        # Get valid token
        token = PasswordResetToken.get_valid_token(email, code)

        if not token:
            logger.warning(f"Invalid or expired reset code attempt for: {email}")
            return Response(
                {"error": "Código inválido o expirado. Por favor, solicita uno nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update password
        user = token.user
        user.set_password(new_password)
        user.save()

        # Mark token as used
        token.used = True
        token.save()

        logger.info(f"Password successfully reset for: {email}")
        return Response(
            {"message": "Contraseña actualizada correctamente."},
            status=status.HTTP_200_OK,
        )
