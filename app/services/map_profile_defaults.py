"""
Plantillas por defecto de tipos de mapa por usuario.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import MapProfile
from app.services.csv_reader import list_denue_csv_basenames

# Nombre visible + comportamiento base del mapa.
DEFAULT_MAP_PROFILES: list[tuple[str, str]] = [
    ("Poligonal del predio", "poligono_predio"),
    ("Riesgos externos (simbología)", "riesgos_simbologia"),
    ("Riesgos externos (numero)", "riesgos_numero"),
    ("Servicio de emergencias", "rutas_emergencia"),
    ("Rutas de acceso a emergencia", "rutas_acceso"),
    ("Puntos de reunión", "puntos_reunion"),
    ("Zonas de mayor riesgo", "zonas_mayor_riesgo"),
]


def _default_csv_layers() -> list[str]:
    data_dir = os.getenv("DATA_DIR", "./DB")
    return list_denue_csv_basenames(data_dir)


def build_default_map_profiles(user_id: UUID, csv_layers: list[str] | None = None) -> list[MapProfile]:
    """
    Crea instancias ORM (sin commit) de perfiles por defecto.

    - `layers`: vacía (sin plantillas de simbología asignadas aún).
    - `csv_layers`: explícita para que el usuario vea capas cargadas desde inicio.
    """
    csv = list(csv_layers if csv_layers is not None else _default_csv_layers())
    return [
        MapProfile(
            id=uuid4(),
            user_id=user_id,
            name=name,
            layers=[],
            csv_layers=list(csv),
            map_vista=vista,
        )
        for name, vista in DEFAULT_MAP_PROFILES
    ]


async def seed_default_map_profiles_for_user(db: AsyncSession, user_id: UUID) -> list[MapProfile]:
    """
    Inserta perfiles por defecto para un usuario (sin commit).
    """
    created = build_default_map_profiles(user_id)
    for mp in created:
        db.add(mp)
    await db.flush()
    return created
