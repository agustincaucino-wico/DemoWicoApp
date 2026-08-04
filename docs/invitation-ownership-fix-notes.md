# DependentInvitation.dependent_user — manual validation notes

Branch: `fix/invitation-ownership-email`

## What was validated

Stage 1 (`ba57654` — nullable `dependent_user` FK on `DependentInvitation`) and
stage 2 (`163d317` — dry-run-by-default backfill command) were manually
validated against the real dev/staging database
(`back-appmobile-tst.wico.com.ar`).

## How

Three synthetic, clearly-marked `DependentInvitation` rows were created on an
existing test holder account, covering the three cases the backfill needs to
distinguish:

1. **Exact-match** — `dependent_email` identical to an existing user's email.
2. **Case-insensitive match** — `dependent_email` same as an existing user's
   email but with different casing.
3. **Unresolved/orphan** — `dependent_email` set to a fake address matching no
   existing user.

The backfill command was run first in dry-run mode, then with `--apply`.

## Result

Both runs resolved all three cases exactly as expected:

- 1 exact-case match
- 1 case-insensitive match
- 1 unresolved (no matching user)
- 0 ambiguous matches

After `--apply`, only `dependent_user_id` changed on the two resolved rows;
all other fields (`dependent_email`, `status`, `holder_account`,
`invitation_date`) were unchanged, and no other row in the table — nor any
other `Account`/`CustomUser` data — was affected.

The three test rows were deleted afterward, restoring the table to its
original empty state on that database.

## Deploying this fix

Once the code is on an environment, the `dependent_user` column has to be
added and populated before the new ownership checks make sense. Pending
invitations whose `dependent_user` is still null can no longer be answered
at all, so the backfill is not optional.

`deploy_dependent_user_migration` chains that sequence and leaves an audit
trail. From the directory containing `manage.py`:

```bash
python manage.py deploy_dependent_user_migration
```

It applies the `accounts` migrations, runs the backfill with `--apply`, and
writes the full report to `<BASE_DIR>/logs/backfill_dependent_user_<timestamp>.log`
(log files are gitignored). Pass `--log-dir` to write the report elsewhere.

Run it **manually, once per environment** — dev/staging and prod — for this
specific fix. It is deliberately not part of the CI/CD pipeline: nothing in
`.github/workflows/` calls it, and it should stay that way, since re-running
a one-off data migration on every future deploy serves no purpose.

Exit codes:

- **0** — migrations and backfill applied, nothing needs manual attention.
- **1** — either the run failed, or the backfill found invitations whose
  email matched more than one user. Ambiguous rows are left untouched for
  manual review, but every unambiguous row is still applied first, so a
  single hard case does not hold up the rest. Resolve those rows by hand
  and re-run to confirm a clean result.

Invitations whose email matches no user at all are reported and logged but
do not fail the run; they are expected and only need reviewing later.

## Not yet done

No validation has been performed against production.
