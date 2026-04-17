"""users: agregar campos atomicos de perfil para registro."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_user_profile_fields"
down_revision = "006_buffer_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("first_name", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("middle_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_name", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("second_last_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "organization", sa.String(length=200), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=20), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "organization")
    op.drop_column("users", "second_last_name")
    op.drop_column("users", "last_name")
    op.drop_column("users", "middle_name")
    op.drop_column("users", "first_name")
