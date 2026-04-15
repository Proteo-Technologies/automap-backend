"""
CRUD de tipos de mapa por usuario: nombre + simbologías visibles + CSV opcional.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbSession
from app.models.orm import MapProfile
from app.schemas.map_profiles import MapProfileCreate, MapProfilePublic, MapProfileUpdate
from app.services.csv_reader import filter_allowed_basenames, list_denue_csv_basenames
from app.services.map_profile_defaults import (
    DEFAULT_GLOBAL_MAP_ACTIONS,
    DEFAULT_ROUTE_MAP_MODES,
    DEFAULT_SYMBOLOGY_MODES,
    seed_default_map_profiles_for_user,
)

router = APIRouter(tags=["map-profiles"])

DATA_DIR = os.getenv("DATA_DIR", "./DB")
RISK_VISTA_BY_MODE: dict[str, str] = {
    "simbologia": "accion_riesgos_simbologia",
    "numero": "accion_riesgos_numero",
}
RISK_MODE_BY_VISTA: dict[str, str] = {
    "accion_riesgos_simbologia": "simbologia",
    "accion_riesgos_numero": "numero",
}

def _all_csv_basenames() -> list[str]:
    files = list_denue_csv_basenames(DATA_DIR)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay archivos CSV en DATA_DIR.",
        )
    return files


def _validate_csv_layers(csv_layers: list[str]) -> list[str]:
    allowed = list_denue_csv_basenames(DATA_DIR)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay archivos CSV en DATA_DIR.",
        )
    if not csv_layers:
        return []
    bad = [x for x in csv_layers if x not in allowed]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivos no disponibles: {', '.join(bad)}",
        )
    return filter_allowed_basenames(csv_layers, allowed)


def _ue_layers_from_profile(mp: MapProfile) -> list[str]:
    raw = mp.layers if isinstance(mp.layers, list) else []
    out: list[str] = []
    seen: set[str] = set()
    for x in raw:
        if not isinstance(x, str):
            continue
        v = x.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


async def _get_owned(
    db: AsyncSession, user_id: UUID, profile_id: UUID
) -> MapProfile | None:
    r = await db.execute(
        select(MapProfile).where(
            MapProfile.id == profile_id,
            MapProfile.user_id == user_id,
        )
    )
    return r.scalar_one_or_none()


def _public(mp: MapProfile) -> MapProfilePublic:
    csv_raw = mp.csv_layers if isinstance(mp.csv_layers, list) else []
    csv_layers = [str(x) for x in csv_raw]
    vista = (mp.map_vista or "denue_general").strip()
    modo_ruta = "normal"
    modo_simbologia = "normal"
    if vista in DEFAULT_ROUTE_MAP_MODES and vista != "normal":
        modo_ruta = vista
    else:
        modo_simbologia = RISK_MODE_BY_VISTA.get(vista, "normal")
    return MapProfilePublic(
        id=mp.id,
        user_id=mp.user_id,
        name=mp.name,
        ue_layers=_ue_layers_from_profile(mp),
        csv_layers=csv_layers,
        map_vista=vista,
        modo_ruta=modo_ruta,
        modo_simbologia=modo_simbologia,
        created_at=mp.created_at,
        updated_at=mp.updated_at,
    )


def _resolve_map_vista(
    map_vista: str | None,
    modo_ruta: str | None,
    modo_simbologia: str | None,
    fallback: str = "denue_general",
) -> str:
    mv = (map_vista or "").strip()
    if mv:
        if mv == "normal":
            return "denue_general"
        if mv in DEFAULT_ROUTE_MAP_MODES or mv in RISK_MODE_BY_VISTA:
            return mv
        if mv == "denue_general":
            return mv
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"map_vista no válido: {mv}",
        )

    mr = (modo_ruta or "").strip().lower()
    ms = (modo_simbologia or "").strip().lower()

    if mr:
        if mr not in DEFAULT_ROUTE_MAP_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"modo_ruta no válido: {mr}",
            )
        if mr != "normal":
            return mr

    if ms:
        if ms not in DEFAULT_SYMBOLOGY_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"modo_simbologia no válido: {ms}",
            )
        if ms != "normal":
            return RISK_VISTA_BY_MODE.get(ms, fallback)

    return fallback


@router.get("", response_model=list[MapProfilePublic])
async def list_profiles(user: CurrentUser, db: DbSession) -> list[MapProfilePublic]:
    q = (
        select(MapProfile)
        .where(MapProfile.user_id == user.id)
        .order_by(MapProfile.name.asc())
    )
    r = await db.execute(q)
    return [_public(x) for x in r.scalars().all()]


@router.get("/global-actions")
async def list_global_map_actions(user: CurrentUser) -> dict:
    """
    Acciones globales de mapa disponibles para cualquier perfil/vista.
    """
    _ = user  # Requiere auth igual que el resto de /map-profiles.
    return {
        "acciones": [
            {"id": action, "label": action.replace("_", " ").replace("accion ", "").title()}
            for action in DEFAULT_GLOBAL_MAP_ACTIONS
        ]
    }


@router.get("/options")
async def list_map_profile_options(user: CurrentUser) -> dict:
    """
    Opciones para formularios de creación/edición de tipos de mapa.
    """
    _ = user
    return {
        "modo_ruta": [
            {"id": x, "label": x.replace("_", " ").title()}
            for x in DEFAULT_ROUTE_MAP_MODES
        ],
        "modo_simbologia": [
            {"id": x, "label": x.replace("_", " ").title()}
            for x in DEFAULT_SYMBOLOGY_MODES
        ],
    }


@router.post("", response_model=MapProfilePublic, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: MapProfileCreate,
    user: CurrentUser,
    db: DbSession,
) -> MapProfilePublic:
    layers = [x.strip() for x in body.ue_layers if x.strip()]
    csv_src = [] if body.csv_layers is None else list(body.csv_layers)
    csv_ok = _validate_csv_layers(csv_src)
    map_vista = _resolve_map_vista(
        body.map_vista,
        body.modo_ruta,
        body.modo_simbologia,
        fallback="denue_general",
    )
    mp = MapProfile(
        id=uuid4(),
        user_id=user.id,
        name=body.name.strip(),
        layers=layers,
        csv_layers=csv_ok,
        map_vista=map_vista,
    )
    db.add(mp)
    await db.commit()
    await db.refresh(mp)
    return _public(mp)


@router.post(
    "/seed-defaults",
    response_model=list[MapProfilePublic],
    status_code=status.HTTP_201_CREATED,
)
async def seed_defaults(user: CurrentUser, db: DbSession) -> list[MapProfilePublic]:
    r = await db.execute(select(MapProfile).where(MapProfile.user_id == user.id))
    if r.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya tienes perfiles. Elimínalos primero o crea tipos manualmente.",
        )
    created = await seed_default_map_profiles_for_user(db, user.id)
    await db.commit()
    for mp in created:
        await db.refresh(mp)
    return [_public(mp) for mp in created]


@router.get("/{profile_id}", response_model=MapProfilePublic)
async def get_profile(
    profile_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> MapProfilePublic:
    mp = await _get_owned(db, user.id, profile_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return _public(mp)


@router.patch("/{profile_id}", response_model=MapProfilePublic)
async def update_profile(
    profile_id: UUID,
    body: MapProfileUpdate,
    user: CurrentUser,
    db: DbSession,
) -> MapProfilePublic:
    mp = await _get_owned(db, user.id, profile_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    if body.name is not None:
        mp.name = body.name.strip()
    if body.ue_layers is not None:
        mp.layers = [x.strip() for x in body.ue_layers if x.strip()]
    if body.csv_layers is not None:
        mp.csv_layers = _validate_csv_layers(list(body.csv_layers))
    if (
        body.map_vista is not None
        or body.modo_ruta is not None
        or body.modo_simbologia is not None
    ):
        mp.map_vista = _resolve_map_vista(
            body.map_vista,
            body.modo_ruta,
            body.modo_simbologia,
            fallback=mp.map_vista or "denue_general",
        )
    await db.commit()
    await db.refresh(mp)
    return _public(mp)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    res = await db.execute(
        delete(MapProfile).where(
            MapProfile.id == profile_id,
            MapProfile.user_id == user.id,
        )
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    await db.commit()
