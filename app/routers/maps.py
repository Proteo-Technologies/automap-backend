"""
CRUD de mapas guardados y borradores (config JSON por proyecto).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession
from app.models.orm import MapProject, SymbologyProfile
from app.schemas.maps import MapProjectCreate, MapProjectPublic, MapProjectUpdate

router = APIRouter(tags=["maps"])


async def _get_map_owned(
    db: AsyncSession, user_id: UUID, map_id: UUID
) -> MapProject | None:
    result = await db.execute(
        select(MapProject).where(
            MapProject.id == map_id,
            MapProject.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


@router.get("", response_model=list[MapProjectPublic])
async def list_maps(
    user: CurrentUser,
    db: DbSession,
    drafts_only: bool | None = Query(default=None),
) -> list[MapProject]:
    q = select(MapProject).where(MapProject.user_id == user.id)
    if drafts_only is True:
        q = q.where(MapProject.is_draft.is_(True))
    elif drafts_only is False:
        q = q.where(MapProject.is_draft.is_(False))
    q = q.order_by(MapProject.updated_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("", response_model=MapProjectPublic, status_code=status.HTTP_201_CREATED)
async def create_map(
    body: MapProjectCreate,
    user: CurrentUser,
    db: DbSession,
) -> MapProject:
    if body.symbology_profile_id is not None:
        sp = await db.execute(
            select(SymbologyProfile).where(
                SymbologyProfile.id == body.symbology_profile_id,
                SymbologyProfile.user_id == user.id,
            )
        )
        if sp.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Simbología no encontrada o no pertenece al usuario",
            )
    mp = MapProject(
        user_id=user.id,
        title=body.title,
        is_draft=body.is_draft,
        config=body.config,
        symbology_profile_id=body.symbology_profile_id,
    )
    db.add(mp)
    await db.commit()
    await db.refresh(mp)
    return mp


@router.get("/{map_id}", response_model=MapProjectPublic)
async def get_map(
    map_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> MapProject:
    mp = await _get_map_owned(db, user.id, map_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="Mapa no encontrado")
    return mp


@router.patch("/{map_id}", response_model=MapProjectPublic)
async def update_map(
    map_id: UUID,
    body: MapProjectUpdate,
    user: CurrentUser,
    db: DbSession,
) -> MapProject:
    mp = await _get_map_owned(db, user.id, map_id)
    if mp is None:
        raise HTTPException(status_code=404, detail="Mapa no encontrado")
    if body.symbology_profile_id is not None:
        sp = await db.execute(
            select(SymbologyProfile).where(
                SymbologyProfile.id == body.symbology_profile_id,
                SymbologyProfile.user_id == user.id,
            )
        )
        if sp.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Simbología no encontrada o no pertenece al usuario",
            )
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(mp, k, v)
    await db.commit()
    await db.refresh(mp)
    return mp


@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map(
    map_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    res = await db.execute(
        delete(MapProject).where(
            MapProject.id == map_id,
            MapProject.user_id == user.id,
        )
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Mapa no encontrado")
    await db.commit()
