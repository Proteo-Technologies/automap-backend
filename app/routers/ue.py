"""
Router: GET /api/unidades-economicas y catálogo de capas CSV.
Filtra registros DENUE por bounding box, prefijos de codigo_act y archivos fuente.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Query

from app.services.csv_reader import (
    Bbox,
    filter_allowed_basenames,
    filtrar_por_bbox,
    list_denue_csv_basenames,
)

router = APIRouter()

DATA_DIR = os.getenv("DATA_DIR", "./DB")
MAX_LIMIT = 5000


def _allowed_csv_files() -> list[str]:
    return list_denue_csv_basenames(DATA_DIR)


def _resolve_files(archivos: Optional[str]) -> list[str]:
    allowed = _allowed_csv_files()
    if not allowed:
        return []
    if not archivos or not archivos.strip():
        return allowed
    req = [a.strip() for a in archivos.split(",") if a.strip()]
    picked = filter_allowed_basenames(req, allowed)
    return picked if picked else allowed


@router.get("/unidades-economicas/capas")
async def list_capas_denue():
    """
    Capas de datos = archivos CSV DENUE disponibles en DATA_DIR.
    """
    files = _allowed_csv_files()
    return {
        "capas": [
            {
                "id": name,
                "label": name.replace(".csv", "").replace("_", " "),
            }
            for name in files
        ],
    }


@router.get("/unidades-economicas")
async def get_unidades_economicas(
    minLat: float = Query(...),
    minLon: float = Query(...),
    maxLat: float = Query(...),
    maxLon: float = Query(...),
    limit: int = Query(default=800, ge=1, le=MAX_LIMIT),
    codigos: Optional[str] = Query(default=None),
    archivos: Optional[str] = Query(
        default=None,
        description="CSV a consultar, separados por coma (basenames). Vacío = todos.",
    ),
):
    bbox = Bbox(
        min_lat=min(minLat, maxLat),
        max_lat=max(minLat, maxLat),
        min_lon=min(minLon, maxLon),
        max_lon=max(minLon, maxLon),
    )

    prefijos: Optional[list[str]] = None
    if codigos:
        prefijos = [c.strip() for c in codigos.split(",") if c.strip()]

    files_to_read = _resolve_files(archivos)
    results: list[dict] = []
    for filename in files_to_read:
        remaining = limit - len(results)
        if remaining <= 0:
            break
        filepath = os.path.join(DATA_DIR, filename)
        partial = filtrar_por_bbox(filepath, bbox, remaining, prefijos)
        results.extend(partial)

    return {"data": results, "total": len(results)}
