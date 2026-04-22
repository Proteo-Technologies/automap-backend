"""
Autenticación: registro, login (JWT), perfil.

Disponibilidad / abuso: límites de tasa por IP (slowapi). Mismo mensaje de error
en login fallido para no filtrar existencia de cuentas (confidencialidad).
"""
from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.core.supabase_auth import validate_supabase_access_token
from app.core.supabase_profile_sync import fetch_profile_and_employee_status
from app.deps import CurrentUser, DbSession
from app.models.orm import User
from app.schemas.auth import SupabaseSSOLogin, Token, UserCreate, UserLogin, UserPublic

router = APIRouter(tags=["auth"])
_log = logging.getLogger(__name__)

_s = get_settings()
_LIMIT_REGISTER = f"{_s.rate_limit_register_per_minute}/minute"
_LIMIT_LOGIN = f"{_s.rate_limit_login_per_minute}/minute"
_LIMIT_SSO = f"{_s.rate_limit_sso_per_minute}/minute"


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
        user = User(
            email=email_norm,
            first_name=body.first_name.strip(),
            middle_name=body.middle_name.strip() if body.middle_name else None,
            last_name=body.last_name.strip(),
            second_last_name=body.second_last_name.strip()
            if body.second_last_name
            else None,
            organization=body.organization.strip(),
            phone=body.phone.strip(),
            hashed_password=hashed,
        )
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


@router.post("/sso/supabase", response_model=Token)
@limiter.limit(_LIMIT_SSO)
async def sso_supabase(request: Request, body: SupabaseSSOLogin, db: DbSession) -> Token:
    try:
        identity = await validate_supabase_access_token(body.access_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token SSO invalido: {exc}",
        ) from exc

    try:
        profile_data, employee_is_active = await fetch_profile_and_employee_status(
            identity.sub, identity.email
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Configuracion SSO incompleta: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        _log.exception("Error consultando perfil/estado en Supabase: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo consultar el perfil ERP en Supabase.",
        ) from exc

    resolved_email = (profile_data.get("email") or identity.email).lower().strip()
    resolved_first_name = (profile_data.get("first_name") or identity.first_name or "Usuario").strip()
    resolved_last_name = (profile_data.get("last_name") or identity.last_name or "ERP").strip()
    resolved_phone = (profile_data.get("phone") or identity.phone or "0000000000").strip()

    result = await db.execute(select(User).where(User.supabase_user_id == identity.sub))
    user = result.scalars().first()

    if user is None:
        by_email = await db.execute(select(User).where(User.email == resolved_email))
        user = by_email.scalars().first()
        if user is None:
            technical_password = secrets.token_urlsafe(48)
            hashed = await asyncio.to_thread(hash_password, technical_password)
            user = User(
                email=resolved_email,
                first_name=resolved_first_name,
                middle_name=identity.middle_name.strip() if identity.middle_name else None,
                last_name=resolved_last_name,
                second_last_name=identity.second_last_name.strip()
                if identity.second_last_name
                else None,
                organization=(identity.organization or "Proteo Atlas").strip(),
                phone=resolved_phone,
                hashed_password=hashed,
                supabase_user_id=identity.sub,
                auth_provider="supabase",
                is_active=True,
            )
            db.add(user)
        else:
            user.supabase_user_id = identity.sub
            user.email = resolved_email
            user.first_name = resolved_first_name
            user.last_name = resolved_last_name
            if resolved_phone:
                user.phone = resolved_phone
            if user.auth_provider == "local":
                user.auth_provider = "hybrid"
    else:
        user.email = resolved_email
        user.first_name = resolved_first_name
        user.last_name = resolved_last_name
        if resolved_phone:
            user.phone = resolved_phone

    if employee_is_active is not None:
        user.is_active = employee_is_active
    elif user.is_active is None:
        # Para usuarios creados en memoria durante este request, evita falso "desactivada".
        user.is_active = True

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada",
        )

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No fue posible enlazar la cuenta SSO. Reintenta.",
        ) from None
    except SQLAlchemyError as e:
        await db.rollback()
        _log.exception("Error de base de datos en sso_supabase: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo iniciar sesion con SSO por un error de base de datos.",
        ) from e

    token = create_access_token(user.id)
    return Token(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> User:
    return user
