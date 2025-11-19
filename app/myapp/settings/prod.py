import os
from pathlib import Path
from .base import *  # noqa
from .base import MIDDLEWARE
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEBUG = False

ALLOWED_HOSTS = [
    "back-appmobile-tst.wico.com.ar",
    "localhost",
    "172.31.25.8",
    "3.21.84.174",
    "174.84.21.3",
    "172.20.0.3",
    "ec2-3-21-84-174.us-east-2.compute.amazonaws.com",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    *MIDDLEWARE,
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME"),
        "USER": os.getenv("DATABASE_USER"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST"),
        "PORT": os.getenv("DATABASE_PORT"),
    },
    "prod": {
        "ENGINE": "django.db.backends.postgresql",
        "OPTIONS": {"options": "-c search_path=wicoapp,public"},
        "NAME": os.getenv("DATABASE_NAME"),
        "USER": os.getenv("DATABASE_USER"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST"),
        "PORT": os.getenv("DATABASE_PORT"),
    },
}


STATIC_URL = "/static/"
STATIC_ROOT = "/appContainer/staticfiles"

ROOT_URLCONF = "myapp.urls"

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)  # Configuración para trabajar detrás de un proxy
USE_X_FORWARDED_HOST = True  # allow Host from proxy
SECURE_SSL_REDIRECT = True  # Redirigir todo el tráfico HTTP a HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Permite hacer llamados a la API desde la web,
# tanto del back office como de la app en web.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8081",  # en prod, reemplazar por la VPN
]

# CSRF Settings for HTTPS
CSRF_TRUSTED_ORIGINS = [
    "https://back-appmobile-tst.wico.com.ar",
    "http://localhost:5000",  # en prod, reemplazar por la VPN
    "http://localhost:8081",  # en prod, reemplazar por la VPN
]


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
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "include_html": True,
        },
        "console": {
            "level": "ERROR",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
    },
}
