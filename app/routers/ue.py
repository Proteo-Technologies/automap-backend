"""
Router: GET /api/unidades-economicas
Filtra registros DENUE por bounding box y (opcionalmente) por prefijos de codigo_act.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.csv_reader import Bbox, filtrar_por_bbox

router = APIRouter()

DATA_DIR = os.getenv("DATA_DIR", "./DB")
CSV_FILES = ["denue_inegi_15_1.csv", "denue_inegi_15_2.csv"]
MAX_LIMIT = 5000


@router.get("/unidades-economicas")
async def get_unidades_economicas(
    minLat: float = Query(...),
    minLon: float = Query(...),
    maxLat: float = Query(...),
    maxLon: float = Query(...),
    limit: int = Query(default=800, ge=1, le=MAX_LIMIT),
    codigos: Optional[str] = Query(default=None),
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

    results: list[dict] = []
    for filename in CSV_FILES:
        remaining = limit - len(results)
        if remaining <= 0:
            break
        filepath = os.path.join(DATA_DIR, filename)
        partial = filtrar_por_bbox(filepath, bbox, remaining, prefijos)
        results.extend(partial)

    return {"data": results, "total": len(results)}
