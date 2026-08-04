"""One-shot deploy helper for the DependentInvitation ownership fix.

Chains the two steps that have to happen together when this fix ships:
apply the accounts migrations (which add DependentInvitation.dependent_user),
then populate that column from the legacy dependent_email string.

Run this MANUALLY, ONCE PER ENVIRONMENT, when deploying the invitation
ownership fix. It is deliberately NOT part of the CI/CD pipeline: nothing
in .github/workflows/ invokes it, and it must not be added there. Wiring
it into the automatic deploy would re-run a one-off data migration on
every future deploy, long after it stopped being meaningful.

Usage (from the directory containing manage.py):

    python manage.py deploy_dependent_user_migration

Exit codes:
    0  migrations applied, backfill applied, nothing needs manual review
    1  ambiguous rows found (the backfill still ran for everything else),
       or the run failed outright

Ordering matters: respond_invitation and accept_invitation reject
invitations whose dependent_user is null, so any pending invitation left
unresolved after this runs can no longer be answered. That is why the
report is written to disk rather than only printed.
"""

import io
import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

MIGRATE_APP_LABEL = "accounts"
BACKFILL_COMMAND = "backfill_dependentinvitation_dependent_user"

# Anchored to the exact lines the backfill command prints. If the report
# format changes, these stop matching and the run fails loudly rather than
# silently reporting zero problems.
AMBIGUOUS_RE = re.compile(
    r"^\s*Unresolved - ambiguous \(>1 match\):\s*(\d+)\s*$", re.MULTILINE
)
NO_MATCH_RE = re.compile(
    r"^\s*Unresolved - no matching user:\s*(\d+)\s*$", re.MULTILINE
)


class Command(BaseCommand):
    help = (
        "Deploy helper for the DependentInvitation ownership fix: applies the "
        "accounts migrations, runs the dependent_user backfill with --apply, "
        "and writes the full report to a timestamped log file.\n\n"
        "Meant to be run manually, once per environment, for this specific "
        "fix. Not part of the automatic deploy pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-dir",
            default=None,
            help=(
                "Directory for the timestamped report (default: <BASE_DIR>/logs). "
                "Created if it does not exist."
            ),
        )

    def handle(self, *args, **options):
        started_at = datetime.now()
        log_dir = Path(options["log_dir"] or Path(settings.BASE_DIR) / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / (
            f"backfill_dependent_user_{started_at:%Y%m%d_%H%M%S}.log"
        )

        transcript = [
            "=== DependentInvitation dependent_user deploy ===",
            f"Started: {started_at:%Y-%m-%d %H:%M:%S}",
            f"Database: {settings.DATABASES['default'].get('NAME')} "
            f"@ {settings.DATABASES['default'].get('HOST')}",
            f"Settings module: {settings.SETTINGS_MODULE}",
            "",
        ]

        def record(text):
            """Send a block to both the log transcript and the console."""
            transcript.append(text)
            self.stdout.write(text)

        # --- step 1: migrations ---------------------------------------
        record(f"--- Step 1: migrate {MIGRATE_APP_LABEL} ---")
        migrate_buffer = io.StringIO()
        try:
            call_command(
                "migrate",
                MIGRATE_APP_LABEL,
                interactive=False,
                stdout=migrate_buffer,
                stderr=migrate_buffer,
            )
        except Exception as exc:
            transcript.append(migrate_buffer.getvalue())
            transcript.append(f"MIGRATION FAILED: {exc}")
            self._write_log(log_path, transcript)
            raise CommandError(
                f"Migrations failed, backfill not attempted. See {log_path}: {exc}"
            )
        record(migrate_buffer.getvalue().rstrip())

        # --- step 2: backfill -----------------------------------------
        record("")
        record(f"--- Step 2: {BACKFILL_COMMAND} --apply ---")
        backfill_buffer = io.StringIO()
        try:
            call_command(
                BACKFILL_COMMAND,
                "--apply",
                stdout=backfill_buffer,
                stderr=backfill_buffer,
            )
        except Exception as exc:
            transcript.append(backfill_buffer.getvalue())
            transcript.append(f"BACKFILL FAILED: {exc}")
            self._write_log(log_path, transcript)
            raise CommandError(f"Backfill failed. See {log_path}: {exc}")

        report = backfill_buffer.getvalue()
        record(report.rstrip())

        # --- step 3: interpret the report -----------------------------
        ambiguous = self._extract_count(AMBIGUOUS_RE, report, "ambiguous", log_path,
                                        transcript)
        no_match = self._extract_count(NO_MATCH_RE, report, "no-match", log_path,
                                       transcript)

        record("")
        record("--- Summary ---")
        # Orphans are expected from time to time and are not a blocker; they
        # are logged so they can be reviewed later.
        record(f"Unresolved (no matching user): {no_match} - not blocking")
        record(f"Ambiguous (>1 match): {ambiguous}")

        finished_at = datetime.now()
        transcript.append("")
        transcript.append(f"Finished: {finished_at:%Y-%m-%d %H:%M:%S}")

        if ambiguous:
            transcript.append(
                f"RESULT: needs manual review ({ambiguous} ambiguous row(s))"
            )
            self._write_log(log_path, transcript)
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"Full report written to {log_path}"))
            # The backfill already committed every unambiguous row above, so
            # the easy cases are resolved; only the ambiguous ones are left.
            raise CommandError(
                f"{ambiguous} invitation(s) matched more than one user by email "
                "and were left unresolved. Every unambiguous row was applied "
                "successfully. Resolve the ambiguous rows manually (see the "
                "sample in the report), then re-run this command to confirm a "
                "clean result."
            )

        transcript.append("RESULT: ok")
        self._write_log(log_path, transcript)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Full report written to {log_path}"))
        self.stdout.write(
            self.style.SUCCESS("Done - no ambiguous rows, no manual review needed.")
        )

    def _extract_count(self, pattern, report, label, log_path, transcript):
        """Pull a count out of the backfill report, refusing to guess."""
        match = pattern.search(report)
        if match is None:
            transcript.append(
                f"COULD NOT PARSE the {label} count from the backfill report."
            )
            self._write_log(log_path, transcript)
            raise CommandError(
                f"Could not find the {label} count in the backfill report. The "
                f"backfill itself ran; its output is in {log_path}. Review it "
                "by hand before treating this deploy as finished."
            )
        return int(match.group(1))

    def _write_log(self, log_path, transcript):
        log_path.write_text("\n".join(transcript) + "\n", encoding="utf-8")
