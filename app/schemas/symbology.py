from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SymbologyCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    rules: dict[str, Any] = Field(default_factory=dict)


class SymbologyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    rules: dict[str, Any] | None = None


class SymbologyPublic(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    rules: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
