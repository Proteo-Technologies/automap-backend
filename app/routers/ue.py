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
    list_supported_categories,
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


@router.get("/unidades-economicas/categorias")
async def list_categorias_denue():
    """
    Catálogo de categorías simplificadas para simbología en frontend.
    """
    cats = list_supported_categories()
    return {
        "categorias": [
            {"id": c, "label": c.replace("_", " ").title()}
            for c in cats
        ]
    }


@router.get("/unidades-economicas")
async def get_unidades_economicas(
    minLat: float = Query(...),
    minLon: float = Query(...),
    maxLat: float = Query(...),
    maxLon: float = Query(...),
    limit: int = Query(default=800, ge=1, le=MAX_LIMIT),
    codigos: Optional[str] = Query(default=None),
    modoCodigos: str = Query(
        default="prefix",
        description='Modo de filtro para `codigos`: "prefix" o "exact".',
    ),
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
    modo_codigos = (modoCodigos or "prefix").strip().lower()
    if modo_codigos not in ("prefix", "exact"):
        modo_codigos = "prefix"

    results: list[dict] = []
    n_files = len(files_to_read)
    if n_files == 0:
        return {"data": [], "total": 0}

    # Repartir cupo entre CSV: aplica con y sin `codigos`.
    # Antes, con prefijos el primer archivo llenaba `limit` y el resto de capas
    # no se consultaba (p. ej. gasolineras solo en el segundo CSV).
    if n_files > 1:
        base = max(1, limit // n_files)
        rema = max(0, limit - (base * n_files))
        for idx, filename in enumerate(files_to_read):
            per_file_limit = base + (1 if idx < rema else 0)
            filepath = os.path.join(DATA_DIR, filename)
            partial = filtrar_por_bbox(
                filepath,
                bbox,
                per_file_limit,
                prefijos,
                modo_codigos=modo_codigos,
            )
            results.extend(partial)
        if len(results) > limit:
            results = results[:limit]
    else:
        filepath = os.path.join(DATA_DIR, files_to_read[0])
        results = filtrar_por_bbox(
            filepath,
            bbox,
            limit,
            prefijos,
            modo_codigos=modo_codigos,
        )

    return {"data": results, "total": len(results)}
