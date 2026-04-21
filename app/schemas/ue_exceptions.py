from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UeExceptionCreate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    codigo_act: str = Field(default="", max_length=32)
    nombre_act: str = Field(default="", max_length=500)
    nom_estab: str = Field(default="", max_length=500)
    categoria: str = Field(default="otros", max_length=120)
    source_file: str | None = Field(default=None, max_length=255)


class UeExceptionPublic(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    user_id: UUID
    lat: float
    lon: float
    codigo_act: str
    nombre_act: str
    nom_estab: str
    categoria: str
    source_file: str | None
    created_at: datetime
