import os
from .base import *  # noqa
from .base import MIDDLEWARE
from dotenv import load_dotenv

load_dotenv()

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

ALLOWED_HOSTS = [
    "back-appmobile-tst.wico.com.ar",
    "172.31.25.8",
]

# Permite hacer llamados a la API desde el back office
CORS_ALLOWED_ORIGINS = ["https://front-intappestacion-tst.wico.com.ar"]

# CSRF Settings for HTTPS
CSRF_TRUSTED_ORIGINS = ["https://front-intappestacion-tst.wico.com.ar"]

GRAPH_MODELS = {
    "all_applications": True,
    "group_models": True,
}

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

STATIC_URL = "/static/"
STATIC_ROOT = "/appContainer/staticfiles"

ROOT_URLCONF = "myapp.urls"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
SERVER_EMAIL = os.getenv("SERVER_EMAIL")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = os.getenv("EMAIL_PORT")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "myapp": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}
