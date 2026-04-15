"""Modelos ORM (PostgreSQL)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    map_projects: Mapped[list["MapProject"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    buffer_presets: Mapped[list["BufferPreset"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    symbology_profiles: Mapped[list["SymbologyProfile"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    map_profiles: Mapped[list["MapProfile"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    ue_exceptions: Mapped[list["UeException"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class MapProfile(Base):
    """Tipo de mapa: nombre, IDs de simbología en `layers`, CSV DENUE opcional."""

    __tablename__ = "map_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    layers: Mapped[list[Any]] = mapped_column(
        JSONB, default=list
    )  # UUIDs de SymbologyProfile (strings); legado ignorado al leer
    csv_layers: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    map_vista: Mapped[str] = mapped_column(String(64), default="denue_general")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="map_profiles")


class SymbologyProfile(Base):
    """
    Plantilla de simbología reutilizable (códigos actividad → color / etiqueta).
    `rules` es un JSON libre acorde al frontend.
    """

    __tablename__ = "symbology_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="symbology_profiles")


class MapProject(Base):
    """
    Mapa guardado o borrador. `config` almacena el estado editable del front
    (coordenadas, escala, capas, simbología aplicada, etc.).
    """

    __tablename__ = "map_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), default="Sin título")
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    symbology_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("symbology_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="map_projects")


class BufferPreset(Base):
    """Buffers reutilizables por usuario (radio y colores)."""

    __tablename__ = "buffer_presets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    radius_meters: Mapped[int] = mapped_column(Integer)
    color_hex: Mapped[str] = mapped_column(String(9))  # #RRGGBB o #RRGGBBAA
    fill_color_hex: Mapped[str | None] = mapped_column(String(9), nullable=True)
    fill_opacity: Mapped[float | None] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped["User"] = relationship(back_populates="buffer_presets")


class UeException(Base):
    """UEs que deben mostrarse aunque queden fuera del buffer/bbox."""

    __tablename__ = "ue_exceptions"
    __table_args__ = (UniqueConstraint("user_id", "ue_key", name="uq_ue_exception_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ue_key: Mapped[str] = mapped_column(String(512), nullable=False)
    lat: Mapped[float] = mapped_column(nullable=False)
    lon: Mapped[float] = mapped_column(nullable=False)
    codigo_act: Mapped[str] = mapped_column(String(32), default="")
    nombre_act: Mapped[str] = mapped_column(Text, default="")
    nom_estab: Mapped[str] = mapped_column(Text, default="")
    categoria: Mapped[str] = mapped_column(String(120), default="otros")
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="ue_exceptions")
