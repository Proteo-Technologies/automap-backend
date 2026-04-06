"""Esquemas Pydantic para perfiles de tipo de mapa (simbología + CSV opcional)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MapProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    ue_layers: list[str] = Field(
        default_factory=list,
        description="Capas UE (categorías) visibles con este tipo de mapa.",
    )
    csv_layers: list[str] | None = Field(
        default=None,
        description="Basenames en DATA_DIR. Vacío u omitido = el cliente consulta todos los CSV.",
    )


class MapProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    ue_layers: list[str] | None = None
    csv_layers: list[str] | None = None


class MapProfilePublic(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    user_id: UUID
    name: str
    ue_layers: list[str]
    csv_layers: list[str]
    map_vista: str
    created_at: datetime
    updated_at: datetime
