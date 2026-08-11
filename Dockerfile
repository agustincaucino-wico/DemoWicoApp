# Imagen del backend para la infra de Wico-Infraestructura (ECR + ASG/EC2,
# ver Workloads/modules/app). Sin nginx delante: el ALB/CloudFront de esa
# infra terminan TLS y balancean directo contra uvicorn en el puerto 8000 -
# nginx.conf (gitignored) era del setup legacy con docker-compose y ya no
# aplica acá. Static files los sirve whitenoise dentro del propio proceso
# (ver requirements.txt / myapp/settings/base.py).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psycopg2-binary no necesita libpq-dev, pero sí un compilador para algunas
# deps transitivas con wheels ausentes para esta arquitectura/versión de Python.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
