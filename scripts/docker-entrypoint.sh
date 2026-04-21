#!/bin/sh
set -e

# Si no hay DATABASE_URL pero sí credenciales del servicio postgres del compose,
# construimos la URL para que coincida con POSTGRES_PASSWORD del mismo despliegue.
if [ -z "$DATABASE_URL" ] && [ -n "$POSTGRES_PASSWORD" ]; then
  PU="${POSTGRES_USER:-automap}"
  PDB="${POSTGRES_DB:-automap}"
  export DATABASE_URL="postgresql+asyncpg://${PU}:${POSTGRES_PASSWORD}@postgres:5432/${PDB}"
  echo "DATABASE_URL vacía: usando postgres del compose (host=postgres, db=${PDB})."
fi

if [ -n "$DATABASE_URL" ]; then
  echo "Aplicando migraciones Alembic..."
  alembic upgrade head
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
