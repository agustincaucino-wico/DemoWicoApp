import os
from pathlib import Path
from .base import *  # noqa
from .base import MIDDLEWARE
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEBUG = False

ALLOWED_HOSTS = ["back-appmobile-tst.wico.com.ar", "localhost", "172.31.25.8"]

MIDDLEWARE = [  # Quitar CORS en producción
    "corsheaders.middleware.CorsMiddleware",
    *MIDDLEWARE,
]

CORS_ALLOW_ALL_ORIGINS = True

STATIC_URL = "/static/"
STATIC_ROOT = "/appContainer/staticfiles"

CORS_ALLOW_ALL_ORIGINS = False

ROOT_URLCONF = "myapp.urls"

# SECURE_HSTS_SECONDS = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True
# SECURE_CONTENT_TYPE_NOSNIFF = True
# SECURE_BROWSER_XSS_FILTER = True
# SECURE_SSL_REDIRECT = False  # change to True when HTTPS is enforced
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# REFERRER_POLICY = "strict-origin-when-cross-origin"

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
