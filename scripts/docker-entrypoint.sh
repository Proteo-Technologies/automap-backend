#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "Aplicando migraciones Alembic..."
  alembic upgrade head
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
