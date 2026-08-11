#!/bin/sh
set -eu

# collectstatic no toca la DB, corre siempre - lo necesita whitenoise para
# servir el admin/swagger UI (no hay nginx delante en esta infra).
python manage.py collectstatic --noinput

# RUN_MIGRATIONS=true solo lo setea el paso de deploy que corre el migrate
# one-shot (ver el workflow) - correr `manage.py migrate` desde el
# entrypoint de CADA contenedor de una ASG con más de una instancia
# (prod corre 2) dispararía migraciones concurrentes en la misma DB.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  python manage.py migrate --noinput
  exit 0
fi

exec uvicorn myapp.asgi:application --host 0.0.0.0 --port 8000
