"""Tabla de excepciones UE por usuario."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_ue_exceptions"
down_revision = "003_map_profile_csv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ue_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ue_key", sa.String(length=512), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("codigo_act", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("nombre_act", sa.Text(), nullable=False, server_default=""),
        sa.Column("nom_estab", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "categoria",
            sa.String(length=120),
            nullable=False,
            server_default="otros",
        ),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ue_key", name="uq_ue_exception_user_key"),
    )
    op.create_index("ix_ue_exceptions_user_id", "ue_exceptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ue_exceptions_user_id", table_name="ue_exceptions")
    op.drop_table("ue_exceptions")
