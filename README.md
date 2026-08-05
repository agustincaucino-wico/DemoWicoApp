# wico-app
Wico app

## Pre-push hook (opt-in)

This repo ships a `.githooks/pre-push` hook: if the push targets `main` or
`PROD`, it tries to run the backend test suite locally first and blocks
the push if a test fails. It's opt-in - Git doesn't use `.githooks/`
automatically, so nothing changes until you run this once per clone:

```bash
git config core.hooksPath .githooks
```

Notes:
- It's a **courtesy safety net, not an enforced gate**. There's no branch
  protection configured on this repo (no admin access to the GitHub repo),
  so nothing server-side actually stops a bad push - CI
  (`.github/workflows/backend-tests.yml`) remains the only real check, and
  the only thing that actually gates deploy.
- It can be skipped entirely with `git push --no-verify`.
- If it can't find a working local Postgres (no `.env`, DB unreachable,
  missing deps, etc.) it prints a loud warning and lets the push through
  rather than blocking on an infrastructure problem - CI still runs either way.
