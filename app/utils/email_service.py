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

    def send_invitation_email(self, holder_user, dependent_user, holder_account):
        """
        Send an invitation email to a user who has been added as a dependent.

        Args:
            holder_user: The user who owns the holder account
            dependent_user: The user who was added as dependent
            holder_account: The holder account object

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        subject = "Invitación WICORED"

        context = {
            "holder_name": holder_user.get_full_name(),
            "holder_email": holder_user.email,
            "account_id": holder_account.id,
            "dependent_email": dependent_user.email,
            "dependent_name": dependent_user.get_full_name(),
        }

        return self.send_email(
            "invitation_email", subject, dependent_user.email, context
        )

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


# Global instance
email_service = EmailService()
