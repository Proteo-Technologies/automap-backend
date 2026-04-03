"""
Autenticación: registro, login (JWT), perfil.

Disponibilidad / abuso: límites de tasa por IP (slowapi). Mismo mensaje de error
en login fallido para no filtrar existencia de cuentas (confidencialidad).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import CurrentUser, DbSession
from app.models.orm import User
from app.schemas.auth import Token, UserCreate, UserLogin, UserPublic

router = APIRouter(tags=["auth"])
_log = logging.getLogger(__name__)

_s = get_settings()
_LIMIT_REGISTER = f"{_s.rate_limit_register_per_minute}/minute"
_LIMIT_LOGIN = f"{_s.rate_limit_login_per_minute}/minute"


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(_LIMIT_REGISTER)
async def register(request: Request, body: UserCreate, db: DbSession) -> User:
    email_norm = body.email.lower().strip()
    existing = await db.execute(select(User).where(User.email == email_norm))
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo",
        )
    try:
        # bcrypt es CPU-bound; en hilo evita rarezas con el loop async.
        hashed = await asyncio.to_thread(hash_password, body.password)
        user = User(email=email_norm, hashed_password=hashed)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo",
        ) from None
    except SQLAlchemyError as e:
        await db.rollback()
        _log.exception("Error de base de datos en register: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar la cuenta. Revisa la base de datos.",
        ) from e


@router.post("/login", response_model=Token)
@limiter.limit(_LIMIT_LOGIN)
async def login(request: Request, body: UserLogin, db: DbSession) -> Token:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalars().first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada",
        )
    token = create_access_token(user.id)
    return Token(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> User:
    return user
