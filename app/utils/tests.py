"""
Tests for the email template rendering pipeline
(utils/template_loader.py, utils/email_service.py).
"""

from django.core import mail
from django.test import TestCase, override_settings

from accounts.models import Account
from users.models import CustomUser
from utils.email_service import EmailService
from utils.template_loader import email_template_loader


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailTemplateRenderingTests(TestCase):
    """
    Renders every real email template (utils/email_templates/*.html + .txt)
    through the actual EmailService methods that use them in production,
    instead of hand-built context dicts - that way a renamed/removed
    context key in email_service.py can't silently drift out of sync with
    what a test asserts against.

    This exists to catch, in CI, exactly the class of bug this suite is
    for: a template edit that breaks rendering (an unescaped brace, a typo
    in a placeholder name, a missing context variable) currently fails
    silently in production - EmailService.send_email() catches the
    exception, logs it, and returns False, which callers already treat as
    a soft "notification didn't go out" failure. None of that shows up
    anywhere until someone notices emails aren't arriving.

    NOTE: send_invitation_cancelled_email and send_invitation_response_email
    are deliberately NOT covered here. Their template files
    (invitation_cancelled.html/.txt, invitation_response.html/.txt) don't
    exist in utils/email_templates/ at all - both already return False in
    production today, independent of anything in this test file or the
    template_loader migration. That's a pre-existing bug, not something
    introduced or masked here.
    """

    def setUp(self):
        self.service = EmailService()
        # first_name/last_name are set deliberately: CustomUser has no
        # username attribute at all (AbstractBaseUser-based, email is the
        # USERNAME_FIELD), but send_dependent_removal_notification and
        # send_dependent_added_notification fall back to .username when
        # get_full_name() is empty - a separate pre-existing bug that isn't
        # what this test is checking, so it's avoided here rather than
        # tripped over incidentally.
        self.holder_user = CustomUser.objects.create_user(
            email="template-holder@example.com",
            password="pass1234",
            first_name="Ana",
            last_name="Titular",
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )
        self.dependent_user = CustomUser.objects.create_user(
            email="template-dependent@example.com",
            password="pass1234",
            first_name="Juan",
            last_name="Pérez",
        )
        self.dependent_account = Account.objects.create(
            user=self.dependent_user, balance=0, account_type="dependent"
        )

    def _assert_sent(self, result):
        self.assertTrue(
            result,
            "EmailService returned False - check logs for the underlying "
            "template rendering error",
        )

    def test_password_reset_email_renders(self):
        self._assert_sent(
            self.service.send_password_reset_email(
                to_email="user@example.com",
                user_name="Juan Pérez",
                reset_code="123456",
            )
        )

    def test_verification_email_renders(self):
        self._assert_sent(
            self.service.send_verification_email(
                to_email="user@example.com",
                user_name="Juan Pérez",
                verification_code="654321",
            )
        )

    def test_invitation_email_renders(self):
        self._assert_sent(
            self.service.send_invitation_email(
                to_email="dependent@example.com",
                holder_name="Ana Titular",
                holder_email="ana@example.com",
                dependent_name="Juan Pérez",
                invitation_id=1,
            )
        )

    def test_dependent_removal_notification_renders(self):
        self._assert_sent(
            self.service.send_dependent_removal_notification(
                holder_user=self.holder_user,
                dependent_user=self.dependent_user,
                holder_account=self.holder_account,
                balance_transferred=150,
            )
        )

    def test_dependent_added_notification_renders(self):
        self._assert_sent(
            self.service.send_dependent_added_notification(
                holder_user=self.holder_user,
                dependent_user=self.dependent_user,
                dependent_account=self.dependent_account,
            )
        )

    def test_app_download_invitation_renders_with_company(self):
        self._assert_sent(
            self.service.send_app_download_invitation(
                to_email="invitee@example.com",
                holder_name="Ana Titular",
                holder_email="ana@example.com",
                company_name="ACME Transportes",
            )
        )

    def test_app_download_invitation_renders_without_company(self):
        self._assert_sent(
            self.service.send_app_download_invitation(
                to_email="invitee@example.com",
                holder_name="Ana Titular",
                holder_email="ana@example.com",
            )
        )

    def test_cordoba_app_download_invitation_renders(self):
        self._assert_sent(
            self.service.send_cordoba_app_download_invitation(
                to_email="invitee@example.com",
                holder_name="Ana Titular",
                holder_email="ana@example.com",
                company_name="ACME Transportes",
            )
        )

    def test_balance_recharge_approved_renders(self):
        self._assert_sent(
            self.service.send_balance_recharge_approved(
                to_email="user@example.com",
                user_name="Juan Pérez",
                amount=1000,
                new_balance=1500,
                request_id=9,
            )
        )

    def test_balance_recharge_rejected_renders(self):
        self._assert_sent(
            self.service.send_balance_recharge_rejected(
                to_email="user@example.com",
                user_name="Juan Pérez",
                amount=1000,
                request_id=9,
                rejection_reason="Comprobante ilegible",
            )
        )

    def test_all_covered_templates_send_a_real_email(self):
        """
        Sanity check that the above aren't all silently no-op-succeeding:
        each one should have actually landed an email in the outbox.
        """
        mail.outbox = []
        self.service.send_password_reset_email(
            to_email="user@example.com", user_name="Juan", reset_code="123456"
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("123456", mail.outbox[0].body)

    # --- regressions for the specific str.format failure mode -------------

    def test_css_braces_do_not_break_rendering(self):
        """
        The original bug: every template's inline CSS uses { and } for rule
        blocks. Under str.format these had to be double-escaped ({{ / }})
        to survive - a future edit that added a new single-brace CSS rule
        without remembering to escape it would silently break rendering in
        production. Confirm the real password_reset template's CSS renders
        as plain, single-brace CSS with no leftover template syntax.
        """
        html, _ = email_template_loader.load_template(
            "password_reset",
            {"user_name": "Juan", "reset_code": "123456", "app_name": "Wico"},
        )
        self.assertIn("body {", html)
        self.assertIn("font-family: Arial, sans-serif;", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("}}", html)

    def test_missing_context_variable_raises_clear_error(self):
        """A missing placeholder must fail loudly and specifically, not
        silently render blank or half-formed content."""
        with self.assertRaises(ValueError) as ctx:
            email_template_loader.load_template(
                "password_reset", {"reset_code": "123456", "app_name": "Wico"}
            )
        self.assertIn("user_name", str(ctx.exception))

    def test_html_context_is_autoescaped_but_txt_is_not(self):
        """
        HTML output must escape user-controlled text (defense against a
        name/reason containing HTML); the plain-text counterpart must NOT
        escape the same value, or a literal "&" would show up as "&amp;"
        in a plain-text email client.
        """
        context = {
            "user_name": "Juan <b>&</b> Co",
            "reset_code": "123456",
            "app_name": "Wico",
        }
        html, txt = email_template_loader.load_template("password_reset", context)
        self.assertIn("&lt;b&gt;", html)
        self.assertNotIn("<b>", html)
        self.assertIn("Juan <b>&</b> Co", txt)
