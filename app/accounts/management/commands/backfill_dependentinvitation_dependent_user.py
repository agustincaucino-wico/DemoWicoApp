from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import DependentInvitation
from users.models import CustomUser


class Command(BaseCommand):
    help = (
        "Stage 2 of the DependentInvitation ownership fix: backfill the "
        "dependent_user FK from the legacy dependent_email string field.\n\n"
        "Defaults to DRY-RUN and writes nothing to the database. Pass "
        "--apply to actually persist the resolved dependent_user values.\n\n"
        "Resolution order per row (only rows with dependent_user IS NULL "
        "are ever considered):\n"
        "  1. Exact-case match against CustomUser.email. email is unique "
        "at the database level, so this can only ever match 0 or 1 users.\n"
        "  2. Case-insensitive (iexact) match, used only as a fallback "
        "when the exact match fails, and only applied if it resolves to "
        "EXACTLY one user.\n\n"
        "CustomUser.email has no case-insensitive uniqueness guarantee at "
        "the database level: it is a plain unique index, which is "
        "case-sensitive, and there is no citext column or functional "
        "lower(email) constraint backing it. Normal registration and "
        "self-service update flows lowercase the email before saving, but "
        "nothing at the schema level stops two accounts from existing that "
        "differ only by letter case (e.g. via the Django admin, which does "
        "not lowercase on save). If an iexact lookup for a row returns "
        "more than one candidate user, this command does NOT guess which "
        "one is the real recipient: the row is left unresolved and "
        "reported separately as 'ambiguous', for manual review.\n\n"
        "Never does fuzzy or partial matching. Never modifies "
        "dependent_email, status, or any field other than dependent_user. "
        "Never touches rows that already have dependent_user set, which "
        "also makes repeated --apply runs a no-op for rows already "
        "resolved by a previous run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help=(
                "Actually write the resolved dependent_user values. "
                "Without this flag, the command only reports what it would do."
            ),
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=10,
            help="Max number of unresolved rows to list per category in the report (default: 10).",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        sample_size = options["sample_size"]

        already_resolved_count = DependentInvitation.objects.filter(
            dependent_user__isnull=False
        ).count()

        candidates = DependentInvitation.objects.filter(
            dependent_user__isnull=True
        ).order_by("id")

        resolved_exact = []
        resolved_case_insensitive = []
        unresolved_no_match = []
        unresolved_ambiguous = []

        for invitation in candidates:
            email = invitation.dependent_email

            exact_match = CustomUser.objects.filter(email=email).first()
            if exact_match is not None:
                resolved_exact.append((invitation, exact_match))
                continue

            ci_matches = list(CustomUser.objects.filter(email__iexact=email)[:2])
            if len(ci_matches) == 1:
                resolved_case_insensitive.append((invitation, ci_matches[0]))
            elif len(ci_matches) == 0:
                unresolved_no_match.append(invitation)
            else:
                unresolved_ambiguous.append(invitation)

        total_checked = (
            len(resolved_exact)
            + len(resolved_case_insensitive)
            + len(unresolved_no_match)
            + len(unresolved_ambiguous)
        )

        if apply_changes:
            with transaction.atomic():
                for invitation, user in resolved_exact:
                    DependentInvitation.objects.filter(pk=invitation.pk).update(
                        dependent_user=user
                    )
                for invitation, user in resolved_case_insensitive:
                    DependentInvitation.objects.filter(pk=invitation.pk).update(
                        dependent_user=user
                    )

        self._print_report(
            apply_changes=apply_changes,
            already_resolved_count=already_resolved_count,
            total_checked=total_checked,
            resolved_exact=resolved_exact,
            resolved_case_insensitive=resolved_case_insensitive,
            unresolved_no_match=unresolved_no_match,
            unresolved_ambiguous=unresolved_ambiguous,
            sample_size=sample_size,
        )

    def _describe(self, invitation):
        return (
            f"invitation_id={invitation.id} "
            f"holder_account_id={invitation.holder_account_id} "
            f"dependent_email={invitation.dependent_email!r} "
            f"status={invitation.status}"
        )

    def _print_report(
        self,
        apply_changes,
        already_resolved_count,
        total_checked,
        resolved_exact,
        resolved_case_insensitive,
        unresolved_no_match,
        unresolved_ambiguous,
        sample_size,
    ):
        mode = "APPLY" if apply_changes else "DRY-RUN"
        w = self.stdout.write

        w(f"=== DependentInvitation.dependent_user backfill ({mode}) ===")
        w(f"Already resolved (skipped, untouched): {already_resolved_count}")
        w(f"Rows checked (dependent_user was null): {total_checked}")
        w(f"  Resolved via exact-case match: {len(resolved_exact)}")
        w(f"  Resolved via case-insensitive match: {len(resolved_case_insensitive)}")
        w(f"  Unresolved - no matching user: {len(unresolved_no_match)}")
        w(f"  Unresolved - ambiguous (>1 match): {len(unresolved_ambiguous)}")

        if unresolved_no_match:
            w("")
            w(f"Unresolved (no match) sample, up to {sample_size}:")
            for invitation in unresolved_no_match[:sample_size]:
                w(f"  {self._describe(invitation)}")

        if unresolved_ambiguous:
            w("")
            w(
                f"Unresolved (ambiguous, needs manual review) sample, up to {sample_size}:"
            )
            for invitation in unresolved_ambiguous[:sample_size]:
                w(f"  {self._describe(invitation)}")

        w("")
        if apply_changes:
            w(
                f"Applied: set dependent_user on "
                f"{len(resolved_exact) + len(resolved_case_insensitive)} row(s)."
            )
        else:
            w("Dry-run: no changes were written. Re-run with --apply to persist them.")
