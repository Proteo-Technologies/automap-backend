"""Validacion de access tokens emitidos por Supabase."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from jose import JWTError, jwk, jwt
from jose.constants import ALGORITHMS
from jose.utils import base64url_decode

from app.core.config import get_settings

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_CACHE_TS = 0.0
_JWKS_TTL_SECONDS = 60 * 10


@dataclass(frozen=True)
class SupabaseIdentity:
    sub: str
    email: str
    first_name: str | None
    middle_name: str | None
    last_name: str | None
    second_last_name: str | None
    organization: str | None
    phone: str | None


def _issuer() -> str:
    settings = get_settings()
    if settings.supabase_jwt_issuer:
        return settings.supabase_jwt_issuer.rstrip("/")
    if settings.supabase_project_url:
        return f"{settings.supabase_project_url.rstrip('/')}/auth/v1"
    raise ValueError("SSO de Supabase no configurado. Define SUPABASE_URL o SUPABASE_JWT_ISSUER.")


async def _get_jwks() -> dict[str, Any]:
    global _JWKS_CACHE, _JWKS_CACHE_TS
    now = time.time()
    if _JWKS_CACHE and now - _JWKS_CACHE_TS < _JWKS_TTL_SECONDS:
        return _JWKS_CACHE

    url = f"{_issuer()}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    if "keys" not in payload:
        raise ValueError("JWKS invalido para Supabase.")
    _JWKS_CACHE = payload
    _JWKS_CACHE_TS = now
    return _JWKS_CACHE


def _select_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    keys = jwks.get("keys", [])
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
    if len(keys) == 1:
        return keys[0]
    raise ValueError("No se encontro la clave publica (kid) para validar el token.")


def _verify_signature(token: str, key_data: dict[str, Any], alg: str) -> None:
    signing_input, encoded_signature = token.rsplit(".", 1)
    decoded_signature = base64url_decode(encoded_signature.encode())
    key = jwk.construct(key_data, algorithm=alg)
    if not key.verify(signing_input.encode(), decoded_signature):
        raise ValueError("Firma JWT invalida.")


def _parse_identity(claims: dict[str, Any]) -> SupabaseIdentity:
    metadata = claims.get("user_metadata") or {}
    app_metadata = claims.get("app_metadata") or {}

    first_name = metadata.get("first_name") or metadata.get("given_name")
    middle_name = metadata.get("middle_name")
    last_name = metadata.get("last_name") or metadata.get("family_name")
    second_last_name = metadata.get("second_last_name")
    organization = metadata.get("organization") or app_metadata.get("organization")
    phone = metadata.get("phone") or claims.get("phone")

    sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not sub or not email:
        raise ValueError("El token de Supabase no contiene sub/email.")

    return SupabaseIdentity(
        sub=sub,
        email=email,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        second_last_name=second_last_name,
        organization=organization,
        phone=phone,
    )


async def validate_supabase_access_token(token: str) -> SupabaseIdentity:
    settings = get_settings()
    expected_issuer = _issuer()

    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        kid = header.get("kid")
        if alg in (ALGORITHMS.RS256, ALGORITHMS.ES256):
            jwks = await _get_jwks()
            key_data = _select_jwk(jwks, kid)
            _verify_signature(token, key_data, alg)
        elif alg == ALGORITHMS.HS256:
            if not settings.supabase_jwt_secret:
                raise ValueError(
                    "Token HS256 recibido. Define SUPABASE_JWT_SECRET para validar SSO."
                )
            jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=[ALGORITHMS.HS256],
                options={
                    "verify_signature": True,
                    "verify_exp": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        else:
            raise ValueError("Algoritmo JWT no permitido para SSO.")

        claims = jwt.get_unverified_claims(token)
        issuer = str(claims.get("iss") or "").rstrip("/")
        if issuer != expected_issuer:
            raise ValueError("Issuer invalido.")

        audience = claims.get("aud")
        expected_audience = settings.supabase_jwt_audience
        if isinstance(audience, list):
            valid_aud = expected_audience in audience
        else:
            valid_aud = audience == expected_audience
        if not valid_aud:
            raise ValueError("Audience invalido.")

        now = int(time.time())
        exp = int(claims.get("exp") or 0)
        if exp <= now:
            raise ValueError("Token expirado.")

        return _parse_identity(claims)
    except (JWTError, ValueError, httpx.HTTPError) as exc:
        raise ValueError(str(exc)) from exc
