"""buffer_presets: agregar bandera is_enabled."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_buffer_enabled"
down_revision = "005_ue_category_exc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "buffer_presets",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("buffer_presets", "is_enabled")
