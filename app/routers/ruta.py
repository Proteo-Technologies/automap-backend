"""
Router: GET /api/ruta
Proxy async hacia Valhalla para calcular rutas viales.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.valhalla import obtener_ruta

router = APIRouter()


@router.get("/ruta")
async def get_ruta(
    latOrigen: float = Query(...),
    lonOrigen: float = Query(...),
    latDest: float = Query(...),
    lonDest: float = Query(...),
):
    try:
        coords = await obtener_ruta(latOrigen, lonOrigen, latDest, lonDest)
        return {"coordinates": coords}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error al consultar servicio de rutas: {exc}",
        ) from exc
