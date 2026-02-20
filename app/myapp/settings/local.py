"""
Local development settings.

Use this when running the API locally on your machine.
- Uses SQLite database (no PostgreSQL needed)
- Console email backend (emails printed to terminal)
- Debug mode enabled
- CORS allows all origins

Usage:
    Set DJANGO_SETTINGS_MODULE='myapp.settings.local' in .env
    Or run: python manage.py runserver --settings=myapp.settings.local
"""

import os
from .base import *  # noqa
from .base import MIDDLEWARE

DEBUG = True

ALLOWED_HOSTS = ["*", "localhost", "127.0.0.1"]

ROOT_URLCONF = "myapp.urls"

CORS_ALLOW_ALL_ORIGINS = True

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

# Console email backend - prints emails to terminal instead of sending
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
SERVER_EMAIL = os.getenv("SERVER_EMAIL")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = os.getenv("EMAIL_PORT")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)


# Static files
STATIC_URL = "/static/"

# Graph models for django-extensions
GRAPH_MODELS = {
    "all_applications": True,
    "group_models": True,
}

# Logging - verbose for local debugging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",  # Set to DEBUG to see SQL queries
            "propagate": False,
        },
        "myapp": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}
