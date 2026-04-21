"""Excepciones por categoria UE (mostrar fuera del bbox)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_ue_category_exc"
down_revision = "004_ue_exceptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ue_category_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("categoria", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "categoria", name="uq_ue_category_exception_user_cat"),
    )
    op.create_index(
        "ix_ue_category_exceptions_user_id", "ue_category_exceptions", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ue_category_exceptions_user_id", table_name="ue_category_exceptions"
    )
    op.drop_table("ue_category_exceptions")
