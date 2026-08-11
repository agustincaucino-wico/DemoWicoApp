"""
Settings for the `wicoapp` dev environment on Wico-Infraestructura
(Workloads/Development, module.wicoapp) - ECR + ASG/EC2 detrás de un ALB
interno y CloudFront+WAF públicos. Ver Workloads/Production/main.tf y
Development/main.tf, módulo `wicoapp`.

Diferencias con dev.py (el settings del servidor legacy):
- ALLOWED_HOSTS = ["*"]: el ALB de este módulo es INTERNO (no tiene IP
  pública, solo lo alcanzan CloudFront vía VPC origin y su propio health
  check) y ya exige el header secreto X-Origin-Verify antes de que la
  request llegue acá (ver modules/alb, listener rule) - Django validando
  Host de nuevo es redundante. Hace falta además porque el health check del
  ALB pega directo a la IP privada de la instancia (Host: <ip>:8000, no un
  dominio), que no se puede enumerar de antemano.
- SECURE_SSL_REDIRECT + SECURE_REDIRECT_EXEMPT para /health/: CloudFront ya
  redirige HTTP->HTTPS en el borde (viewer_protocol_policy, ver modules/cdn)
  así que todo tráfico real llega con X-Forwarded-Proto=https. Pero el
  health check del ALB pega directo al target por HTTP, sin ese header - sin
  la excepción, Django le devolvería un 301 y el ALB marcaría la instancia
  unhealthy.
- Sin MEDIA_ROOT en disco persistente (el /mnt de dev.py no existe en estas
  instancias, y aunque existiera no sobrevive a un reemplazo de ASG). Usa el
  default de base.py (disco local del contenedor) - se pierde en cada
  redeploy/reemplazo de instancia. Migrar a los buckets S3 que ya provisiona
  modules/storage (app_docs/app_tmp/app_imagenes/...) es un follow-up, no
  algo que este cambio resuelva.
"""

import os
from .base import *  # noqa
from .base import MIDDLEWARE
from dotenv import load_dotenv

load_dotenv()

DEBUG = False

ALLOWED_HOSTS = ["*"]

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

ROOT_URLCONF = "myapp.urls"

# Sin frontend propio todavía (module.wicoapp no instancia private_frontend
# ni tiene subdominio de frontend público) - agregar el origin acá cuando
# exista.
CORS_ALLOWED_ORIGINS = []
CSRF_TRUSTED_ORIGINS = ["https://api-wicoapp-dev.wicosistemas.com.ar"]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/?$"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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
