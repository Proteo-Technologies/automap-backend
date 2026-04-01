"""
Punto de entrada de la API FastAPI – Automap Backend.

Arrancar en desarrollo:
    uvicorn app.main:app --reload --port 8000

Variables de entorno (.env):
    PORT            Puerto (default 8000, solo aplica si usas el script run.py)
    DATA_DIR        Ruta a la carpeta con los CSV DENUE (default ./DB)
    ALLOWED_ORIGINS URLs del frontend permitidas para CORS (separadas por coma)
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, ruta, ue

load_dotenv()

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001",
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app = FastAPI(
    title="Automap API",
    description="API para mapas cartográficos DENUE – Mapa del Entorno del Proyecto",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(ue.router, prefix="/api")
app.include_router(ruta.router, prefix="/api")
app.include_router(health.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "Automap API activa",
        "docs": "/docs",
        "endpoints": [
            "/api/unidades-economicas",
            "/api/ruta",
            "/api/health",
        ],
    }
