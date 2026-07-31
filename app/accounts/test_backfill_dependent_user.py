"""Tests for the backfill_dependentinvitation_dependent_user management command.

Stage 2 of the DependentInvitation ownership fix: this command populates
the dependent_user FK (added in stage 1) from the legacy dependent_email
string field. It must never be run against a real environment as part of
these tests - everything here runs against the ephemeral test database.
"""

from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import Account, DependentInvitation
from users.models import CustomUser

COMMAND_NAME = "backfill_dependentinvitation_dependent_user"


def _snapshot(instance):
    """Return every column of instance, straight from the database."""
    instance.refresh_from_db()
    return {
        field.attname: getattr(instance, field.attname)
        for field in instance._meta.fields
    }


class BackfillDependentUserCommandTests(TestCase):
    def setUp(self):
        self.holder_user = CustomUser.objects.create_user(
            email="holder@example.com", password="pass1234"
        )
        self.holder_account = Account.objects.get(
            user=self.holder_user, account_type="holder"
        )

    def _make_invitation(self, dependent_email, dependent_user=None, status="pending"):
        return DependentInvitation.objects.create(
            holder_account=self.holder_account,
            dependent_email=dependent_email,
            dependent_user=dependent_user,
            status=status,
        )

    def _run(self, *args):
        out = StringIO()
        call_command(COMMAND_NAME, *args, stdout=out)
        return out.getvalue()

    # --- dry-run safety ------------------------------------------------

    def test_dry_run_makes_zero_database_writes(self):
        invitee = CustomUser.objects.create_user(
            email="invitee@example.com", password="pass1234"
        )
        invitation = self._make_invitation(dependent_email=invitee.email)

        with CaptureQueriesContext(connection) as ctx:
            self._run()  # no --apply: must default to dry-run

        write_queries = [
            q
            for q in ctx.captured_queries
            if q["sql"].strip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
        ]
        self.assertEqual(
            write_queries, [], f"dry-run executed write queries: {write_queries}"
        )

        invitation.refresh_from_db()
        self.assertIsNone(invitation.dependent_user_id)

    def test_dry_run_reports_would_be_resolution_without_applying(self):
        invitee = CustomUser.objects.create_user(
            email="invitee2@example.com", password="pass1234"
        )
        self._make_invitation(dependent_email=invitee.email)

        output = self._run()

        self.assertIn("DRY-RUN", output)
        self.assertRegex(output, r"Resolved via exact-case match:\s*1\b")
        self.assertIn("no changes were written", output)

    # --- resolution logic ------------------------------------------------

    def test_resolves_exact_case_match_on_apply(self):
        invitee = CustomUser.objects.create_user(
            email="exact@example.com", password="pass1234"
        )
        invitation = self._make_invitation(dependent_email="exact@example.com")

        self._run("--apply")

        invitation.refresh_from_db()
        self.assertEqual(invitation.dependent_user_id, invitee.id)

    def test_resolves_case_insensitive_fallback_on_apply(self):
        invitee = CustomUser.objects.create_user(
            email="mixedcase@example.com", password="pass1234"
        )
        # dependent_email stored with different case than the user's
        # actual, lowercased-on-registration email.
        invitation = self._make_invitation(dependent_email="MixedCase@Example.com")

        self._run("--apply")

        invitation.refresh_from_db()
        self.assertEqual(invitation.dependent_user_id, invitee.id)

    def test_unmatched_row_left_alone_and_reported(self):
        invitation = self._make_invitation(dependent_email="nobody@example.com")

        output = self._run("--apply")

        invitation.refresh_from_db()
        self.assertIsNone(invitation.dependent_user_id)
        self.assertRegex(output, r"Unresolved - no matching user:\s*1\b")
        self.assertIn(f"invitation_id={invitation.id}", output)
        self.assertIn("dependent_email='nobody@example.com'", output)

    def test_ambiguous_case_insensitive_matches_left_unresolved(self):
        # Bypass CustomUserManager.create_user (which lowercases on save)
        # to simulate two accounts differing only by letter case. This is
        # possible today because CustomUser.email only has a plain,
        # case-sensitive unique index at the database level - e.g. an
        # admin edit that doesn't go through the serializer/manager could
        # produce this.
        user_a = CustomUser(email="Dup@Example.com")
        user_a.set_unusable_password()
        user_a.save()
        user_b = CustomUser(email="dup@example.com")
        user_b.set_unusable_password()
        user_b.save()

        invitation = self._make_invitation(dependent_email="DUP@example.com")

        output = self._run("--apply")

        invitation.refresh_from_db()
        self.assertIsNone(invitation.dependent_user_id)
        self.assertRegex(output, r"Unresolved - ambiguous \(>1 match\):\s*1\b")
        self.assertIn(f"invitation_id={invitation.id}", output)

    # --- idempotency and non-interference ---------------------------------

    def test_apply_twice_is_idempotent(self):
        invitee = CustomUser.objects.create_user(
            email="idempotent@example.com", password="pass1234"
        )
        invitation = self._make_invitation(dependent_email=invitee.email)

        self._run("--apply")
        state_after_first = _snapshot(invitation)

        self._run("--apply")
        state_after_second = _snapshot(invitation)

        self.assertEqual(state_after_first, state_after_second)
        self.assertEqual(state_after_second["dependent_user_id"], invitee.id)

    def test_apply_twice_does_not_touch_unresolved_rows_either(self):
        invitation = self._make_invitation(dependent_email="stillnobody@example.com")

        self._run("--apply")
        state_after_first = _snapshot(invitation)

        self._run("--apply")
        state_after_second = _snapshot(invitation)

        self.assertEqual(state_after_first, state_after_second)
        self.assertIsNone(state_after_second["dependent_user_id"])

    def test_already_resolved_row_is_never_touched_or_recounted(self):
        invitee = CustomUser.objects.create_user(
            email="already@example.com", password="pass1234"
        )
        other_user = CustomUser.objects.create_user(
            email="other@example.com", password="pass1234"
        )
        # Pre-resolved to other_user, but dependent_email deliberately
        # left pointing at invitee: if the command re-evaluated this row
        # it would try to "fix" it to invitee. It must not.
        invitation = self._make_invitation(
            dependent_email=invitee.email, dependent_user=other_user
        )

        output = self._run("--apply")

        invitation.refresh_from_db()
        self.assertEqual(invitation.dependent_user_id, other_user.id)
        self.assertIn("Already resolved (skipped, untouched): 1", output)
        self.assertIn("Rows checked (dependent_user was null): 0", output)

    def test_only_dependent_user_field_is_ever_modified(self):
        invitee = CustomUser.objects.create_user(
            email="fieldcheck@example.com", password="pass1234"
        )
        invitation = self._make_invitation(dependent_email=invitee.email)

        before_invitation = _snapshot(invitation)
        before_user = _snapshot(invitee)

        self._run("--apply")

        after_invitation = _snapshot(invitation)
        after_user = _snapshot(invitee)

        self.assertIsNone(before_invitation["dependent_user_id"])
        self.assertEqual(after_invitation["dependent_user_id"], invitee.id)

        diff_keys = {
            key
            for key in before_invitation
            if before_invitation[key] != after_invitation[key]
        }
        self.assertEqual(diff_keys, {"dependent_user_id"})

        # The matched CustomUser row must be completely untouched.
        self.assertEqual(before_user, after_user)

    def test_report_lists_sample_of_unresolved_rows_for_manual_review(self):
        invitation = self._make_invitation(dependent_email="orphan@example.com")

        output = self._run("--apply", "--sample-size=5")

        self.assertIn(f"invitation_id={invitation.id}", output)
        self.assertIn(f"holder_account_id={self.holder_account.id}", output)
        self.assertIn("status=pending", output)
