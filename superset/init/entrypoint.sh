#!/bin/bash
# Entrypoint del contenedor de un solo uso "superset-init". Deja el
# sistema completamente listo (esquema de metadatos, admin, dashboard)
# antes de que arranquen los contenedores de larga duración "superset" y
# "superset-worker" (ver "depends_on: condition: service_completed_successfully"
# en docker-compose.yml).
set -euo pipefail

echo "[init] Migrando base de metadatos de Superset..."
superset db upgrade

echo "[init] Creando usuario administrador (si no existe)..."
set +e
superset fab create-admin \
    --username "$ADMIN_USERNAME" \
    --firstname "$ADMIN_FIRSTNAME" \
    --lastname "$ADMIN_LASTNAME" \
    --email "$ADMIN_EMAIL" \
    --password "$ADMIN_PASSWORD"
set -e

echo "[init] Inicializando roles y permisos..."
superset init

echo "[init] Levantando servidor temporal en 127.0.0.1:8088 para usar la API REST..."
gunicorn --bind 127.0.0.1:8088 --workers 1 --timeout 120 "superset.app:create_app()" &
GUNICORN_PID=$!
trap 'kill $GUNICORN_PID 2>/dev/null || true' EXIT

echo "[init] Ejecutando bootstrap del dashboard (conexión, dataset, métricas, gráficos, dashboard)..."
python3 /app/init/bootstrap_dashboard.py

echo "[init] Deteniendo servidor temporal..."
kill "$GUNICORN_PID"
wait "$GUNICORN_PID" 2>/dev/null || true

echo "[init] superset-init completado con éxito."
