from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UeCategoryExceptionCreate(BaseModel):
    categoria: str = Field(..., min_length=1, max_length=120)


class UeCategoryExceptionPublic(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    user_id: UUID
    categoria: str
    created_at: datetime
