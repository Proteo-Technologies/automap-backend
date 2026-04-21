"""
Cabeceras HTTP orientadas a la tríada CIA:
- Confidencialidad / integridad del contexto del cliente (navegador): anti-MIME, anti-clickjacking.
- No sustituyen TLS: el cifrado en tránsito debe configurarse en el proxy (HTTPS).
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras de seguridad estándar a todas las respuestas."""

    def __init__(
        self,
        app,
        *,
        hsts_max_age: int = 0,
    ) -> None:
        super().__init__(app)
        self._hsts_max_age = hsts_max_age

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
        )
        # Evita cacheo intermedio de respuestas con datos potencialmente sensibles (API JSON).
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if self._hsts_max_age > 0:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={self._hsts_max_age}; includeSubDomains"
            )
        return response
