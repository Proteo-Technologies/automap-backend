"""
Comprobaciones al arranque alineadas con la tríada CIA (mínimo viable).

- Confidencialidad: secreto JWT fuerte en entornos expuestos.
- Integridad: evitar valores por defecto inseguros en producción.
- Disponibilidad: fallar pronto si la configuración es inválida (evita servicio “a medias”).
"""
from __future__ import annotations

from app.core.config import Settings

# Secreto por defecto del código — nunca usar en producción con DATABASE_URL.
_FORBIDDEN_JWT_SECRETS = frozenset(
    {
        "cambiar-en-produccion-usa-secreto-largo-aleatorio",
    }
)


def validate_security_settings(settings: Settings) -> None:
    """Lanza RuntimeError si la configuración es inaceptable para el entorno declarado."""
    if settings.environment == "development":
        return

    if settings.database_url and settings.jwt_secret in _FORBIDDEN_JWT_SECRETS:
        raise RuntimeError(
            "Seguridad (integridad/confidencialidad): define JWT_SECRET distinto del valor "
            "por defecto cuando ENV no es development y DATABASE_URL está configurada."
        )

    if settings.database_url and len(settings.jwt_secret) < settings.jwt_secret_min_length:
        raise RuntimeError(
            f"Seguridad (confidencialidad): JWT_SECRET debe tener al menos "
            f"{settings.jwt_secret_min_length} caracteres si ENV=staging|production y hay DATABASE_URL."
        )
