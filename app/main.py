"""
Punto de entrada de la API FastAPI – Automap Backend.

Seguridad (tríada CIA — mínimo):
- Confidencialidad: JWT firmado con secreto fuerte en producción; TLS en el proxy.
- Integridad: validación de entrada (Pydantic), ORM parametrizado, cabeceras anti-MIME/iframe.
- Disponibilidad: límites de tasa en login/registro; fallo rápido si la config es inválida.

Arrancar en desarrollo:
    uvicorn app.main:app --reload --port 8000

Variables de entorno (.env):
    PORT            Puerto (default 8000, solo aplica si usas el script run.py)
    DATA_DIR        Ruta a la carpeta con los CSV DENUE (default ./DB)
    ALLOWED_ORIGINS URLs del frontend permitidas para CORS (separadas por coma)
    DATABASE_URL    postgresql+asyncpg://user:pass@host:5432/db (opcional; requerido para auth/mapas)
    JWT_SECRET      Secreto para firmar JWT (obligatorio en producción si hay DATABASE_URL)
    ENV             development | staging | production (afecta validación de secretos)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.startup_checks import validate_security_settings
from app.db.session import configure_db
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import auth, buffer_presets, health, map_profiles, maps, ruta, symbology, ue

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001",
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_settings(_settings)
    if _settings.database_url:
        configure_db(_settings.database_url)
    yield


app = FastAPI(
    title="Automap API",
    description="API para mapas cartográficos DENUE – Mapa del Entorno del Proyecto",
    version="1.1.0",
    lifespan=lifespan,
    openapi_url="/openapi.json" if _settings.expose_api_docs else None,
    docs_url="/docs" if _settings.expose_api_docs else None,
    redoc_url="/redoc" if _settings.expose_api_docs else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: lista explícita + en development cualquier puerto de localhost (evita bloqueos si Next usa 3001, 3002, etc.)
_cors_kw: dict = {
    "allow_origins": ALLOWED_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["*"],
}
if _settings.environment == "development":
    _cors_kw["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

# CORS el último = capa más externa: las respuestas de error también llevan Access-Control-Allow-Origin.
app.add_middleware(
    SecurityHeadersMiddleware,
    hsts_max_age=_settings.hsts_seconds,
)
app.add_middleware(CORSMiddleware, **_cors_kw)

app.include_router(ue.router, prefix="/api")
app.include_router(ruta.router, prefix="/api")
app.include_router(health.router, prefix="/api")

app.include_router(auth.router, prefix="/api/auth")
app.include_router(maps.router, prefix="/api/maps")
app.include_router(map_profiles.router, prefix="/api/map-profiles")
app.include_router(buffer_presets.router, prefix="/api/buffer-presets")
app.include_router(symbology.router, prefix="/api/symbology-profiles")


@app.get("/")
async def root():
    return {
        "message": "Automap API activa",
        "docs": "/docs",
        "endpoints": [
            "/api/unidades-economicas",
            "/api/unidades-economicas/capas",
            "/api/unidades-economicas/excepciones",
            "/api/unidades-economicas/excepciones-por-categoria",
            "/api/ruta",
            "/api/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/maps",
            "/api/map-profiles",
            "/api/buffer-presets",
            "/api/symbology-profiles",
        ],
    }
