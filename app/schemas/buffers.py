from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class BufferPresetCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    radius_meters: int = Field(ge=1, le=500_000)
    color_hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
    fill_color_hex: str | None = Field(
        default=None, pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"
    )
    fill_opacity: float | None = Field(default=None, ge=0, le=1)
    sort_order: int = 0


class BufferPresetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    radius_meters: int | None = Field(default=None, ge=1, le=500_000)
    color_hex: str | None = Field(
        default=None, pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"
    )
    fill_color_hex: str | None = Field(
        default=None, pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"
    )
    fill_opacity: float | None = Field(default=None, ge=0, le=1)
    sort_order: int | None = None


class BufferPresetPublic(BaseModel):
    id: UUID
    user_id: UUID
    name: str | None
    radius_meters: int
    color_hex: str
    fill_color_hex: str | None
    fill_opacity: float | None
    sort_order: int

    model_config = {"from_attributes": True}
