"""Campos de usuario para SSO con Supabase."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_users_supabase_sso"
down_revision = "008_map_profile_modo_simb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("supabase_user_id", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=32),
            nullable=False,
            server_default="local",
        ),
    )
    op.create_index("ix_users_supabase_user_id", "users", ["supabase_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_supabase_user_id", table_name="users")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "supabase_user_id")
