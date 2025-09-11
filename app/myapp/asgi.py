"""
ASGI config for myapp project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from dotenv import load_dotenv
from django.core.asgi import get_asgi_application

dotenv_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".env"
)
load_dotenv(dotenv_path)

# Esto usará el valor de la variable de entorno si existe, y como fallback: app.myapp.settings.prod
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.myapp.settings.prod")

application = get_asgi_application()
