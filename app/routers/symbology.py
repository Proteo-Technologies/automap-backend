"""
Plantillas de simbología reutilizables por usuario.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbSession
from app.models.orm import SymbologyProfile
from app.schemas.symbology import SymbologyCreate, SymbologyPublic, SymbologyUpdate

router = APIRouter(tags=["symbology"])


@router.get("", response_model=list[SymbologyPublic])
async def list_profiles(user: CurrentUser, db: DbSession) -> list[SymbologyProfile]:
    result = await db.execute(
        select(SymbologyProfile)
        .where(SymbologyProfile.user_id == user.id)
        .order_by(SymbologyProfile.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=SymbologyPublic, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: SymbologyCreate,
    user: CurrentUser,
    db: DbSession,
) -> SymbologyProfile:
    sp = SymbologyProfile(
        user_id=user.id,
        name=body.name,
        description=body.description,
        rules=body.rules,
    )
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return sp


@router.get("/{profile_id}", response_model=SymbologyPublic)
async def get_profile(
    profile_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> SymbologyProfile:
    result = await db.execute(
        select(SymbologyProfile).where(
            SymbologyProfile.id == profile_id,
            SymbologyProfile.user_id == user.id,
        )
    )
    sp = result.scalar_one_or_none()
    if sp is None:
        raise HTTPException(status_code=404, detail="Simbología no encontrada")
    return sp


@router.patch("/{profile_id}", response_model=SymbologyPublic)
async def update_profile(
    profile_id: UUID,
    body: SymbologyUpdate,
    user: CurrentUser,
    db: DbSession,
) -> SymbologyProfile:
    result = await db.execute(
        select(SymbologyProfile).where(
            SymbologyProfile.id == profile_id,
            SymbologyProfile.user_id == user.id,
        )
    )
    sp = result.scalar_one_or_none()
    if sp is None:
        raise HTTPException(status_code=404, detail="Simbología no encontrada")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(sp, k, v)
    await db.commit()
    await db.refresh(sp)
    return sp


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    res = await db.execute(
        delete(SymbologyProfile).where(
            SymbologyProfile.id == profile_id,
            SymbologyProfile.user_id == user.id,
        )
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Simbología no encontrada")
    await db.commit()
