"""
CRUD de tipos de mapa por usuario: nombre + simbologías visibles + CSV opcional.
"""
from __future__ import annotations

import os
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession
from app.models.orm import MapProfile, SymbologyProfile
from app.schemas.map_profiles import MapProfileCreate, MapProfilePublic, MapProfileUpdate
from app.services.csv_reader import filter_allowed_basenames, list_denue_csv_basenames

router = APIRouter(tags=["map-profiles"])

DATA_DIR = os.getenv("DATA_DIR", "./DB")

_UUID_STR_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


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


async def _validate_symbology_ids(
    db: AsyncSession, user_id: UUID, ids: list[UUID]
) -> list[str]:
    if not ids:
        return []
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    r = await db.execute(
        select(SymbologyProfile.id).where(
            SymbologyProfile.user_id == user_id,
            SymbologyProfile.id.in_(ordered),
        )
    )
    found = {row[0] for row in r.all()}
    missing = [str(i) for i in ordered if i not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Simbología no encontrada o no es tuya: {', '.join(missing)}",
        )
    return [str(i) for i in ordered]


def _symbology_ids_from_layers(mp: MapProfile) -> list[str]:
    raw = mp.layers if isinstance(mp.layers, list) else []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and _UUID_STR_RE.match(x.strip()):
            out.append(x.strip().lower())
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
    return MapProfilePublic(
        id=mp.id,
        user_id=mp.user_id,
        name=mp.name,
        symbology_profile_ids=_symbology_ids_from_layers(mp),
        csv_layers=csv_layers,
        map_vista=mp.map_vista or "denue_general",
        created_at=mp.created_at,
        updated_at=mp.updated_at,
    )


@router.get("", response_model=list[MapProfilePublic])
async def list_profiles(user: CurrentUser, db: DbSession) -> list[MapProfilePublic]:
    q = (
        select(MapProfile)
        .where(MapProfile.user_id == user.id)
        .order_by(MapProfile.name.asc())
    )
    r = await db.execute(q)
    return [_public(x) for x in r.scalars().all()]


@router.post("", response_model=MapProfilePublic, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: MapProfileCreate,
    user: CurrentUser,
    db: DbSession,
) -> MapProfilePublic:
    sym_strings = await _validate_symbology_ids(db, user.id, list(body.symbology_profile_ids))
    csv_src = [] if body.csv_layers is None else list(body.csv_layers)
    csv_ok = _validate_csv_layers(csv_src)
    mp = MapProfile(
        id=uuid4(),
        user_id=user.id,
        name=body.name.strip(),
        layers=sym_strings,
        csv_layers=csv_ok,
        map_vista="denue_general",
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
    csv_all = _all_csv_basenames()
    mp = MapProfile(
        id=uuid4(),
        user_id=user.id,
        name="Unidades económicas (plantilla)",
        layers=[],
        csv_layers=list(csv_all),
        map_vista="denue_general",
    )
    db.add(mp)
    await db.commit()
    await db.refresh(mp)
    return [_public(mp)]


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
    if body.symbology_profile_ids is not None:
        sym_strings = await _validate_symbology_ids(
            db, user.id, list(body.symbology_profile_ids)
        )
        mp.layers = sym_strings
        mp.map_vista = "denue_general"
    if body.csv_layers is not None:
        mp.csv_layers = _validate_csv_layers(list(body.csv_layers))
        mp.map_vista = "denue_general"
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
