"""
Presets de buffers (radio y colores) por usuario.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbSession
from app.models.orm import BufferPreset
from app.schemas.buffers import BufferPresetCreate, BufferPresetPublic, BufferPresetUpdate

router = APIRouter(tags=["buffer-presets"])


@router.get("", response_model=list[BufferPresetPublic])
async def list_presets(user: CurrentUser, db: DbSession) -> list[BufferPreset]:
    result = await db.execute(
        select(BufferPreset)
        .where(BufferPreset.user_id == user.id)
        .order_by(BufferPreset.sort_order, BufferPreset.radius_meters)
    )
    return list(result.scalars().all())


@router.post("", response_model=BufferPresetPublic, status_code=status.HTTP_201_CREATED)
async def create_preset(
    body: BufferPresetCreate,
    user: CurrentUser,
    db: DbSession,
) -> BufferPreset:
    bp = BufferPreset(
        user_id=user.id,
        name=body.name,
        radius_meters=body.radius_meters,
        color_hex=body.color_hex,
        fill_color_hex=body.fill_color_hex,
        fill_opacity=body.fill_opacity,
        sort_order=body.sort_order,
    )
    db.add(bp)
    await db.commit()
    await db.refresh(bp)
    return bp


@router.patch("/{preset_id}", response_model=BufferPresetPublic)
async def update_preset(
    preset_id: UUID,
    body: BufferPresetUpdate,
    user: CurrentUser,
    db: DbSession,
) -> BufferPreset:
    result = await db.execute(
        select(BufferPreset).where(
            BufferPreset.id == preset_id,
            BufferPreset.user_id == user.id,
        )
    )
    bp = result.scalar_one_or_none()
    if bp is None:
        raise HTTPException(status_code=404, detail="Buffer no encontrado")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(bp, k, v)
    await db.commit()
    await db.refresh(bp)
    return bp


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(
    preset_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    res = await db.execute(
        delete(BufferPreset).where(
            BufferPreset.id == preset_id,
            BufferPreset.user_id == user.id,
        )
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Buffer no encontrado")
    await db.commit()
