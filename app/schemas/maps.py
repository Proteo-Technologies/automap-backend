from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MapProjectCreate(BaseModel):
    title: str = Field(default="Sin título", max_length=500)
    is_draft: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    symbology_profile_id: UUID | None = None


class MapProjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    is_draft: bool | None = None
    config: dict[str, Any] | None = None
    symbology_profile_id: UUID | None = None


class MapProjectPublic(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    is_draft: bool
    config: dict[str, Any]
    symbology_profile_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
