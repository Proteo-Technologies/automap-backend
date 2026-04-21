"""map_profiles: agregar columna modo_simbologia independiente de map_vista."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "008_map_profile_modo_simb"
down_revision = "007_user_profile_fields"
branch_labels = None
depends_on = None


# Mapeo histórico: perfiles que nacieron como `accion_riesgos_*` conservan su
# modo de simbología aunque cambiemos `map_vista` (no los perdemos al migrar).
_VISTA_TO_SIMB: dict[str, str] = {
    "accion_riesgos_simbologia": "simbologia",
    "accion_riesgos_numero": "numero",
    "riesgos_simbologia": "simbologia",
    "riesgos_numero": "numero",
}


def upgrade() -> None:
    op.add_column(
        "map_profiles",
        sa.Column(
            "modo_simbologia",
            sa.String(length=32),
            nullable=False,
            server_default="normal",
        ),
    )

    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, map_vista FROM map_profiles")).fetchall()
    for row in rows:
        rid = row[0]
        vista = row[1] or ""
        modo = _VISTA_TO_SIMB.get(vista)
        if not modo:
            continue
        conn.execute(
            text("UPDATE map_profiles SET modo_simbologia = :m WHERE id = :id"),
            {"m": modo, "id": rid},
        )


def downgrade() -> None:
    op.drop_column("map_profiles", "modo_simbologia")
