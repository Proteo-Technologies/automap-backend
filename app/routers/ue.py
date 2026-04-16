"""
Router: GET /api/unidades-economicas y catálogo de capas CSV.
Filtra registros DENUE por bounding box, prefijos de codigo_act y archivos fuente.
"""
from __future__ import annotations

import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select

from app.core.security import decode_token
from app.db.session import db_configured, get_session_factory
from app.deps import CurrentUser, DbSession
from app.models.orm import UeCategoryException, UeException
from app.schemas.ue_category_exceptions import (
    UeCategoryExceptionCreate,
    UeCategoryExceptionPublic,
)
from app.schemas.ue_exceptions import UeExceptionCreate, UeExceptionPublic
from app.services.csv_reader import (
    Bbox,
    filter_allowed_basenames,
    filtrar_fuera_bbox_por_categorias,
    filtrar_por_bbox,
    list_denue_csv_basenames,
    list_supported_categories,
)

router = APIRouter()
security = HTTPBearer(auto_error=False)

DATA_DIR = os.getenv("DATA_DIR", "./DB")
MAX_LIMIT = 5000


def _build_ue_key(
    lat: float,
    lon: float,
    codigo_act: str,
    nombre_act: str,
    nom_estab: str,
) -> str:
    lat_key = f"{lat:.6f}"
    lon_key = f"{lon:.6f}"
    return "|".join(
        [
            lat_key,
            lon_key,
            (codigo_act or "").strip().lower(),
            (nombre_act or "").strip().lower(),
            (nom_estab or "").strip().lower(),
        ]
    )


def _ue_key_from_dict(item: dict) -> str:
    return _build_ue_key(
        float(item.get("lat", 0.0)),
        float(item.get("lon", 0.0)),
        str(item.get("codigo_act", "")),
        str(item.get("nombre_act", "")),
        str(item.get("nom_estab", "")),
    )


def _user_id_from_credentials(credentials: HTTPAuthorizationCredentials | None):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta Authorization: Bearer <token> para incluir excepciones UE.",
        )
    uid = decode_token(credentials.credentials)
    if uid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
        )
    return uid


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


@router.get(
    "/unidades-economicas/excepciones",
    response_model=list[UeExceptionPublic],
)
async def list_ue_excepciones(
    user: CurrentUser,
    db: DbSession,
) -> list[UeException]:
    result = await db.execute(
        select(UeException)
        .where(UeException.user_id == user.id)
        .order_by(UeException.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/unidades-economicas/excepciones",
    response_model=UeExceptionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_ue_excepcion(
    body: UeExceptionCreate,
    user: CurrentUser,
    db: DbSession,
) -> UeException:
    ue_key = _build_ue_key(
        body.lat,
        body.lon,
        body.codigo_act,
        body.nombre_act,
        body.nom_estab,
    )
    existing = await db.execute(
        select(UeException).where(
            UeException.user_id == user.id,
            UeException.ue_key == ue_key,
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found

    item = UeException(
        user_id=user.id,
        ue_key=ue_key,
        lat=body.lat,
        lon=body.lon,
        codigo_act=body.codigo_act.strip(),
        nombre_act=body.nombre_act.strip(),
        nom_estab=body.nom_estab.strip(),
        categoria=(body.categoria or "otros").strip() or "otros",
        source_file=(body.source_file.strip() if body.source_file else None),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete(
    "/unidades-economicas/excepciones/{exception_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ue_excepcion(
    exception_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    res = await db.execute(
        delete(UeException).where(
            UeException.id == exception_id,
            UeException.user_id == user.id,
        )
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Excepción UE no encontrada")
    await db.commit()


def _validar_categoria_catalogo(categoria: str) -> str:
    cat = (categoria or "").strip()
    allowed = set(list_supported_categories())
    if cat not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Categoría no válida: {categoria}. Use GET /api/unidades-economicas/categorias.",
        )
    return cat


@router.get(
    "/unidades-economicas/excepciones-por-categoria",
    response_model=list[UeCategoryExceptionPublic],
)
async def list_ue_excepciones_por_categoria(
    user: CurrentUser,
    db: DbSession,
) -> list[UeCategoryException]:
    result = await db.execute(
        select(UeCategoryException)
        .where(UeCategoryException.user_id == user.id)
        .order_by(UeCategoryException.categoria.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/unidades-economicas/excepciones-por-categoria",
    response_model=UeCategoryExceptionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_ue_excepcion_por_categoria(
    body: UeCategoryExceptionCreate,
    user: CurrentUser,
    db: DbSession,
) -> UeCategoryException:
    cat = _validar_categoria_catalogo(body.categoria)
    existing = await db.execute(
        select(UeCategoryException).where(
            UeCategoryException.user_id == user.id,
            UeCategoryException.categoria == cat,
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found

    item = UeCategoryException(user_id=user.id, categoria=cat)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete(
    "/unidades-economicas/excepciones-por-categoria/{exception_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ue_excepcion_por_categoria(
    exception_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    res = await db.execute(
        delete(UeCategoryException).where(
            UeCategoryException.id == exception_id,
            UeCategoryException.user_id == user.id,
        )
    )
    if res.rowcount == 0:
        raise HTTPException(
            status_code=404, detail="Excepción por categoría no encontrada"
        )
    await db.commit()


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
    incluirExcepciones: bool = Query(
        default=False,
        description="Si es true, agrega UEs por categoría y/o excepciones puntuales fuera del bbox.",
    ),
    limiteExcepcionesFuera: int = Query(
        default=3000,
        ge=0,
        le=10000,
        description="Tope de UEs extra fuera del bbox por categorías configuradas (0 = no agregar por categoría).",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
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

    if not incluirExcepciones:
        return {"data": results, "total": len(results)}

    if not db_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no configurada para consultar excepciones UE.",
        )

    user_id = _user_id_from_credentials(credentials)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible.",
        )

    seen = {_ue_key_from_dict(x) for x in results}

    async with factory() as session:
        rows_cat = await session.execute(
            select(UeCategoryException).where(UeCategoryException.user_id == user_id)
        )
        categorias_exc = {
            str(x.categoria).strip()
            for x in rows_cat.scalars().all()
            if x.categoria
        }

        rows_ue = await session.execute(
            select(UeException).where(UeException.user_id == user_id)
        )
        excepciones_ue = list(rows_ue.scalars().all())

    # 1) Todas las UEs de categorías marcadas, fuera del bbox (mismo filtro codigos/archivos).
    if categorias_exc and limiteExcepcionesFuera > 0:
        cats_set = {c for c in categorias_exc if c in set(list_supported_categories())}
        if cats_set:
            if n_files > 1:
                base_e = max(1, limiteExcepcionesFuera // n_files)
                rema_e = max(0, limiteExcepcionesFuera - (base_e * n_files))
                for idx, filename in enumerate(files_to_read):
                    per_lim = base_e + (1 if idx < rema_e else 0)
                    filepath = os.path.join(DATA_DIR, filename)
                    extra = filtrar_fuera_bbox_por_categorias(
                        filepath,
                        bbox,
                        cats_set,
                        per_lim,
                        prefijos,
                        modo_codigos=modo_codigos,
                    )
                    for ue in extra:
                        k = _ue_key_from_dict(ue)
                        if k in seen:
                            continue
                        seen.add(k)
                        results.append(ue)
            else:
                filepath = os.path.join(DATA_DIR, files_to_read[0])
                extra = filtrar_fuera_bbox_por_categorias(
                    filepath,
                    bbox,
                    cats_set,
                    limiteExcepcionesFuera,
                    prefijos,
                    modo_codigos=modo_codigos,
                )
                for ue in extra:
                    k = _ue_key_from_dict(ue)
                    if k in seen:
                        continue
                    seen.add(k)
                    results.append(ue)

    # 2) Excepciones puntuales (legacy): UEs guardadas una a una.
    for ex in excepciones_ue:
        ue = {
            "lat": ex.lat,
            "lon": ex.lon,
            "codigo_act": ex.codigo_act,
            "nombre_act": ex.nombre_act,
            "nom_estab": ex.nom_estab,
            "categoria": ex.categoria or "otros",
            "source_file": ex.source_file,
            "is_exception": True,
            "exception_reason": "ue_manual",
        }
        k = _ue_key_from_dict(ue)
        if k in seen:
            continue
        seen.add(k)
        results.append(ue)

    return {"data": results, "total": len(results)}
