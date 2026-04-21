"""
Router: GET /api/ruta
Proxy async hacia Valhalla para calcular rutas viales.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.valhalla import obtener_ruta, obtener_rutas

router = APIRouter()

ROUTE_TYPE_ALIASES: dict[str, str] = {
    "ruta_ue_a_coordenada": "ue_a_coordenada",
    "ruta_coordenada_a_ue": "coordenada_a_ue",
    "ruta_reunion_a_ue": "reunion_a_ue",
    "ruta_coordenada_ue_ida_vuelta": "coordenada_ue_ida_vuelta",
}


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


@router.get("/rutas-operativas")
async def get_rutas_operativas(
    tipo: Literal[
        "ue_a_coordenada",
        "coordenada_a_ue",
        "reunion_a_ue",
        "coordenada_ue_ida_vuelta",
        "ruta_ue_a_coordenada",
        "ruta_coordenada_a_ue",
        "ruta_reunion_a_ue",
        "ruta_coordenada_ue_ida_vuelta",
    ] = Query(..., description="Tipo de operación de ruta."),
    ueLat: float = Query(..., ge=-90, le=90),
    ueLon: float = Query(..., ge=-180, le=180),
    coordLat: Optional[float] = Query(default=None, ge=-90, le=90),
    coordLon: Optional[float] = Query(default=None, ge=-180, le=180),
    reunionLat: Optional[float] = Query(default=None, ge=-90, le=90),
    reunionLon: Optional[float] = Query(default=None, ge=-180, le=180),
):
    """
    Devuelve rutas operativas según caso de uso:
    - ue_a_coordenada: hasta 3 rutas alternativas UE -> coordenada.
    - coordenada_a_ue: 1 ruta coordenada -> UE.
    - reunion_a_ue: 1 ruta punto de reunión -> UE (requiere punto).
    - coordenada_ue_ida_vuelta: 2 rutas (ida y regreso).
    """
    try:
        tipo_normalizado = ROUTE_TYPE_ALIASES.get(tipo, tipo)
        rutas: list[dict] = []

        if tipo_normalizado == "ue_a_coordenada":
            if coordLat is None or coordLon is None:
                raise HTTPException(
                    status_code=422,
                    detail="Para `ue_a_coordenada` se requieren coordLat y coordLon.",
                )
            alternativas = await obtener_rutas(
                ueLat, ueLon, coordLat, coordLon, alternativas=3
            )
            rutas = [
                {"id": f"alternativa_{i + 1}", "sentido": "ida", "coordinates": coords}
                for i, coords in enumerate(alternativas)
            ]

        elif tipo_normalizado == "coordenada_a_ue":
            if coordLat is None or coordLon is None:
                raise HTTPException(
                    status_code=422,
                    detail="Para `coordenada_a_ue` se requieren coordLat y coordLon.",
                )
            coords = await obtener_ruta(coordLat, coordLon, ueLat, ueLon)
            rutas = [{"id": "principal", "sentido": "ida", "coordinates": coords}]

        elif tipo_normalizado == "reunion_a_ue":
            if reunionLat is None or reunionLon is None:
                raise HTTPException(
                    status_code=422,
                    detail="No hay punto de reunión: se requieren reunionLat y reunionLon.",
                )
            # Evita rutas triviales cuando frontend envía por error el mismo punto.
            if abs(reunionLat - ueLat) < 1e-7 and abs(reunionLon - ueLon) < 1e-7:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Punto de reunión inválido: coincide con la UE. "
                        "Verifica las coordenadas seleccionadas en frontend."
                    ),
                )
            coords = await obtener_ruta(reunionLat, reunionLon, ueLat, ueLon)
            rutas = [{"id": "principal", "sentido": "ida", "coordinates": coords}]

        elif tipo_normalizado == "coordenada_ue_ida_vuelta":
            if coordLat is None or coordLon is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Para `coordenada_ue_ida_vuelta` se requieren coordLat y coordLon."
                    ),
                )
            ida = await obtener_ruta(coordLat, coordLon, ueLat, ueLon)
            vuelta = await obtener_ruta(ueLat, ueLon, coordLat, coordLon)
            rutas = [
                {"id": "ida", "sentido": "ida", "coordinates": ida},
                {"id": "vuelta", "sentido": "vuelta", "coordinates": vuelta},
            ]

        return {"tipo": tipo_normalizado, "total": len(rutas), "rutas": rutas}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error al consultar servicio de rutas: {exc}",
        ) from exc
