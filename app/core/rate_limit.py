"""
Limitación de peticiones (disponibilidad: mitiga abuso y fuerza bruta sobre auth).
Tras un proxy de confianza, usa TRUSTED_PROXY + X-Forwarded-For para la IP cliente.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_ip_key_func(request: Request) -> str:
    """
    IP para cuotas. Si TRUSTED_PROXY está activado, toma el primer salto de
    X-Forwarded-For (solo detrás de un proxy que sobrescriba cabeceras no confiables).
    """
    from app.core.config import get_settings

    settings = get_settings()
    if settings.trusted_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip_key_func)
