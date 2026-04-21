"""map_profiles: archivos CSV (capas) + map_vista."""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "003_map_profile_csv"
down_revision = "002_map_profiles"
branch_labels = None
depends_on = None

DEFAULT_CSV = ["denue_inegi_15_1.csv", "denue_inegi_15_2.csv"]


def _infer_vista(layers: list | None) -> str:
    if not layers:
        return "denue_general"
    s = set(layers)
    if "poligono_predio" in s:
        return "poligono_predio"
    if "puntos_reunion" in s:
        return "puntos_reunion"
    if "ue_riesgos_numero" in s:
        return "riesgos_numero"
    if "ue_zonas_mayor_riesgo" in s:
        return "zonas_mayor_riesgo"
    if "ue_riesgos_simbologia" in s:
        return "riesgos_simbologia"
    if "trazado_ue_a_centro" in s and "centro_marcador_buffers" in s:
        return "rutas_acceso"
    if "trazado_centro_a_ue" in s and "centro_marcador_buffers" in s:
        return "rutas_emergencia"
    return "denue_general"


def upgrade() -> None:
    op.add_column(
        "map_profiles",
        sa.Column(
            "csv_layers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "map_profiles",
        sa.Column(
            "map_vista",
            sa.String(64),
            nullable=False,
            server_default="denue_general",
        ),
    )

    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, layers FROM map_profiles")).fetchall()
    csv_json = json.dumps(DEFAULT_CSV)
    for row in rows:
        rid = row[0]
        raw = row[1]
        layers_list: list | None
        if raw is None:
            layers_list = []
        elif isinstance(raw, list):
            layers_list = raw
        elif isinstance(raw, str):
            try:
                layers_list = json.loads(raw)
            except json.JSONDecodeError:
                layers_list = []
        else:
            layers_list = []
        vista = _infer_vista(layers_list)
        conn.execute(
            text(
                "UPDATE map_profiles SET csv_layers = CAST(:c AS jsonb), map_vista = :v "
                "WHERE id = :id"
            ),
            {"c": csv_json, "v": vista, "id": rid},
        )


def downgrade() -> None:
    op.drop_column("map_profiles", "map_vista")
    op.drop_column("map_profiles", "csv_layers")
