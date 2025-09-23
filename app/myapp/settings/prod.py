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
]

# # -- Quitar CORS en producción
# MIDDLEWARE = [
#     "corsheaders.middleware.CorsMiddleware",
#     *MIDDLEWARE,
# ]

# CORS_ALLOW_ALL_ORIGINS = True
# ---

STATIC_URL = "/static/"
STATIC_ROOT = "/appContainer/staticfiles"

ROOT_URLCONF = "myapp.urls"

# SECURE_HSTS_SECONDS = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True
# SECURE_CONTENT_TYPE_NOSNIFF = True
# REFERRER_POLICY = "strict-origin-when-cross-origin"
# SECURE_BROWSER_XSS_FILTER = True
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)  # Configuración para trabajar detrás de un proxy
USE_X_FORWARDED_HOST = True  # allow Host from proxy
SECURE_SSL_REDIRECT = True  # Redirigir todo el tráfico HTTP a HTTPS
CORS_ALLOWED_ORIGINS = [
    "https://back-appmobile-tst.wico.com.ar",
]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

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
LOGGING["loggers"]["django.security.csrf"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}
