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

## Not yet done

No validation has been performed against production.
