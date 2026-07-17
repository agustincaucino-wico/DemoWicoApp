"""
Settings for running the automated test suite / CI.

Inherits everything from the base settings and overrides only what's
needed for a clean, isolated test run:

- DATABASES / ROOT_URLCONF: structurally required (base.py defines
  neither), using the same env-driven Postgres connection as dev.py so
  the DB tests already run against doesn't change.
- MEDIA_ROOT: a temp directory instead of dev.py's "/mnt/backend-appmobile-tst",
  which doesn't exist outside the dev/tst host and isn't meant to be
  written to by tests.
- EMAIL_BACKEND: locmem, so send_mail actually "succeeds" and lands in
  mail.outbox instead of trying a real SMTP connection and silently
  returning False (which is what dev.py's smtp backend does today,
  turning any un-mocked email-sending assertion into a false failure).
- DEBUG: False, matching what the suite already assumes (see
  users/tests.py::DevUserLoginViewTests, which pins the DEBUG-gated
  endpoint's off-state, and PasswordResetToken.MAX_REQUESTS_PER_HOUR,
  which is baked to its DEBUG=False value at import time).
"""

import os
import tempfile

from dotenv import load_dotenv

from .base import *  # noqa
from .base import MIDDLEWARE

load_dotenv()

DEBUG = False

ROOT_URLCONF = "myapp.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME"),
        "USER": os.getenv("DATABASE_USER"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST"),
        "PORT": os.getenv("DATABASE_PORT"),
        "OPTIONS": {"options": "-c search_path=public"},
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Not cleaned up automatically - left for the OS/CI runner to reclaim /tmp,
# same as the per-class tempfile.mkdtemp() pattern in operation/tests.py.
MEDIA_ROOT = tempfile.mkdtemp(prefix="wico-test-media-")
MEDIA_URL = "/media/"
