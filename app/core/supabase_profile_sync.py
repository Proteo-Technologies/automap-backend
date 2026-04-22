"""Consulta perfiles/estado en Supabase para sincronizar usuarios locales."""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


def _coerce_employee_active(status_value: object, end_date_value: object) -> bool | None:
    if isinstance(status_value, bool):
        return status_value
    if isinstance(status_value, (int, float)):
        return bool(status_value)
    if isinstance(status_value, str):
        normalized = status_value.strip().lower()
        if normalized in {"active", "activo", "enabled", "habilitado"}:
            return True
        if normalized in {"inactive", "inactivo", "disabled", "baja", "terminated"}:
            return False
    if end_date_value is not None:
        return False
    return None


def _rest_base_url() -> str:
    settings = get_settings()
    if not settings.supabase_project_url:
        raise ValueError("Define SUPABASE_URL para sincronizar perfiles ERP.")
    return f"{settings.supabase_project_url.rstrip('/')}/rest/v1"


def _service_headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise ValueError(
            "Define SUPABASE_SERVICE_ROLE_KEY para leer profiles/employees de Supabase."
        )
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }


async def fetch_profile_and_employee_status(
    supabase_user_id: str, email_fallback: str | None
) -> tuple[dict[str, str | None], bool | None]:
    """
    Lee perfil y estado laboral desde Supabase REST (schema public).
    Retorna (profile_data, employee_is_active).
    """
    profile_data = {"email": None, "first_name": None, "last_name": None, "phone": None}
    employee_is_active: bool | None = None
    base_url = _rest_base_url()
    headers = _service_headers()

    async with httpx.AsyncClient(timeout=10.0) as client:
        profile_resp = await client.get(
            f"{base_url}/profiles",
            headers=headers,
            params={
                "user_id": f"eq.{supabase_user_id}",
                "select": "name,last_name,email,phone",
                "limit": "1",
            },
        )
        profile_resp.raise_for_status()
        profile_rows = profile_resp.json()
        if isinstance(profile_rows, list) and profile_rows:
            row = profile_rows[0]
            profile_data = {
                "email": (str(row.get("email")).strip().lower() if row.get("email") else None),
                "first_name": (str(row.get("name")).strip() if row.get("name") else None),
                "last_name": (str(row.get("last_name")).strip() if row.get("last_name") else None),
                "phone": (str(row.get("phone")).strip() if row.get("phone") else None),
            }
        elif email_fallback:
            profile_resp_by_email = await client.get(
                f"{base_url}/profiles",
                headers=headers,
                params={
                    "email": f"eq.{email_fallback.lower().strip()}",
                    "select": "name,last_name,email,phone",
                    "limit": "1",
                },
            )
            profile_resp_by_email.raise_for_status()
            profile_rows_email = profile_resp_by_email.json()
            if isinstance(profile_rows_email, list) and profile_rows_email:
                row = profile_rows_email[0]
                profile_data = {
                    "email": (str(row.get("email")).strip().lower() if row.get("email") else None),
                    "first_name": (str(row.get("name")).strip() if row.get("name") else None),
                    "last_name": (str(row.get("last_name")).strip() if row.get("last_name") else None),
                    "phone": (str(row.get("phone")).strip() if row.get("phone") else None),
                }

        employee_resp = await client.get(
            f"{base_url}/employees",
            headers=headers,
            params={
                "user_id": f"eq.{supabase_user_id}",
                "select": "status,end_date,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        employee_resp.raise_for_status()
        employee_rows: Any = employee_resp.json()
        if isinstance(employee_rows, list) and employee_rows:
            employee = employee_rows[0]
            employee_is_active = _coerce_employee_active(
                employee.get("status"),
                employee.get("end_date"),
            )

    return profile_data, employee_is_active
