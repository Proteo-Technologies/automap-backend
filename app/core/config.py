"""Configuración central (env / .env)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    """postgresql+asyncpg://user:pass@host:5432/db"""

    jwt_secret: str = "cambiar-en-produccion-usa-secreto-largo-aleatorio"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 días

    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="ENV",
    )
    """Entorno de despliegue. En `production` se aplican comprobaciones de secreto JWT."""

    jwt_secret_min_length: int = 32
    """Longitud mínima de JWT_SECRET si ENV=production y hay base de datos."""

    trusted_proxy: bool = Field(
        default=False,
        validation_alias="TRUSTED_PROXY",
    )
    """
    True solo si la API está detrás de un proxy que inyecta X-Forwarded-For fiable.
    Afecta a la limitación por IP (rate limiting).
    """

    expose_api_docs: bool = Field(default=True, validation_alias="EXPOSE_API_DOCS")
    """Expone /docs y /openapi.json. Desactivar en producción expuesta a Internet."""

    hsts_seconds: int = Field(default=0, validation_alias="HSTS_SECONDS")
    """
    Si > 0 y la terminación TLS es correcta, envía Strict-Transport-Security (solo tiene
    sentido detrás de HTTPS).
    """

    # Cuotas auth (disponibilidad / abuso)
    rate_limit_login_per_minute: int = Field(default=15, ge=1, le=300)
    rate_limit_register_per_minute: int = Field(default=8, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
