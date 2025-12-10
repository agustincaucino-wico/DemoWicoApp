"""
Email service for sending various types of notifications.
"""

from django.core.mail import send_mail
from django.conf import settings
import logging

from .template_loader import email_template_loader

logger = logging.getLogger(__name__)


class EmailService:
    """Service class for handling email operations."""

    def __init__(self):
        self.from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@wico.app")
        self.app_name = getattr(settings, "APP_NAME", "Wico")

    def send_email(self, template_name, subject, recipient_email, context):
        """
        Generic method to send emails using templates.

        Args:
            template_name: Name of the email template
            subject: Email subject
            recipient_email: Recipient's email address
            context: Context variables for the template

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            # Add app_name to context if not present
            if "app_name" not in context:
                context["app_name"] = self.app_name

            # Load templates
            html_content, text_content = email_template_loader.load_template(
                template_name, context
            )

            # Send email
            send_mail(
                subject=subject,
                message=text_content,
                from_email=self.from_email,
                recipient_list=[recipient_email],
                html_message=html_content,
                fail_silently=False,
            )

            logger.info(
                f"Email '{template_name}' sent successfully to {recipient_email}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send email '{template_name}' to {recipient_email}: {str(e)}"
            )
            return False

    def send_invitation_email(
        self, to_email, holder_name, holder_email, dependent_name, invitation_id
    ):
        """
        Send an invitation email to a user who has been invited as a dependent.

        Args:
            to_email: Email address of the dependent (recipient)
            holder_name: Full name of the holder who sent the invitation
            holder_email: Email address of the holder
            dependent_name: Name of the dependent user (or email if name not available)
            invitation_id: ID of the invitation

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        subject = "Invitación WICORED"

        context = {
            "holder_name": holder_name,
            "holder_email": holder_email,
            "dependent_name": dependent_name,
            "invitation_id": invitation_id,
        }

        return self.send_email("invitation_email", subject, to_email, context)

    def send_dependent_removal_notification(
        self, holder_user, dependent_user, holder_account
    ):
        """
        Send a notification email when a dependent is removed from an account.

        Args:
            holder_user: The user who owns the holder account
            dependent_user: The user who was removed as dependent
            holder_account: The holder account object

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        subject = "Remoción de cuenta adherida WICORED"

        context = {
            "holder_name": holder_user.get_full_name() or holder_user.username,
            "holder_email": holder_user.email,
            "dependent_name": dependent_user.get_full_name() or dependent_user.username,
            "dependent_email": dependent_user.email,
            "account_id": holder_account.id,
        }

        return self.send_email(
            "removal_notification", subject, dependent_user.email, context
        )

    def send_invitation_response_email(self, to_email, dependent_name, action):
        """
        Send an email notification when a dependent responds to an invitation.

        Args:
            to_email: Email address of the holder (recipient)
            dependent_name: Full name of the dependent who responded
            action: The action taken ('accept' or 'reject')

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        action_text = "aceptó" if action == "accept" else "rechazó"
        subject = f"Respuesta a invitación WICORED - {action_text}"

        context = {
            "dependent_name": dependent_name,
            "action": action,
            "action_text": action_text,
        }

        return self.send_email("invitation_response", subject, to_email, context)

    def send_invitation_cancelled_email(self, to_email, holder_name):
        """
        Send an email notification when a holder cancels a pending invitation.

        Args:
            to_email: Email address of the dependent (recipient)
            holder_name: Full name of the holder who cancelled the invitation

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        subject = "Invitación cancelada - WICORED"

        context = {
            "holder_name": holder_name,
        }

        return self.send_email("invitation_cancelled", subject, to_email, context)

    def send_password_reset_email(self, to_email, user_name, reset_code):
        """
        Send a password reset code email.

        Args:
            to_email: Email address of the user
            user_name: Name of the user (or email if name not available)
            reset_code: The 6-digit reset code

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        subject = "Código de recuperación de contraseña - WICO"

        context = {
            "user_name": user_name,
            "reset_code": reset_code,
        }

        return self.send_email("password_reset", subject, to_email, context)


# Global instance
email_service = EmailService()
