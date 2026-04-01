"""
Lectura y filtrado de archivos CSV DENUE usando pandas.

Las columnas relevantes son posicionales (igual que en el server.js original):
  - índice 4  → codigo_act
  - índice 5  → nombre_act
  - índice -3 → latitud
  - índice -2 → longitud
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Bbox:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


def _leer_csv(filepath: str) -> pd.DataFrame:
    """Lee un CSV DENUE ignorando el BOM y devuelve un DataFrame crudo."""
    return pd.read_csv(
        filepath,
        header=0,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
        on_bad_lines="skip",
    )


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Extrae las columnas necesarias por índice posicional."""
    cols = df.columns.tolist()
    n = len(cols)
    if n < 6:
        return pd.DataFrame(columns=["lat", "lon", "codigo_act", "nombre_act"])

    col_lat = cols[n - 3]
    col_lon = cols[n - 2]
    col_codigo = cols[4]
    col_nombre = cols[5]

    out = df[[col_codigo, col_nombre, col_lat, col_lon]].copy()
    out.columns = ["codigo_act", "nombre_act", "lat", "lon"]
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    out = out.dropna(subset=["lat", "lon"])
    out["codigo_act"] = out["codigo_act"].fillna("").str.strip()
    out["nombre_act"] = out["nombre_act"].fillna("").str.strip()
    return out


def filtrar_por_bbox(
    filepath: str,
    bbox: Bbox,
    limit: int,
    prefijos: Optional[list[str]] = None,
) -> list[dict]:
    """
    Devuelve hasta `limit` registros del CSV que estén dentro del bbox.
    Si se pasan `prefijos`, solo incluye registros cuyo codigo_act empiece
    con alguno de ellos.
    """
    if not os.path.exists(filepath):
        return []

    df = _leer_csv(filepath)
    df = _normalizar(df)

    mask = (
        (df["lat"] >= bbox.min_lat)
        & (df["lat"] <= bbox.max_lat)
        & (df["lon"] >= bbox.min_lon)
        & (df["lon"] <= bbox.max_lon)
    )

    if prefijos:
        prefix_mask = df["codigo_act"].apply(
            lambda c: any(c.startswith(p) for p in prefijos)
        )
        mask = mask & prefix_mask

    resultado = df[mask].head(limit)
    return resultado[["lat", "lon", "codigo_act", "nombre_act"]].to_dict(
        orient="records"
    )
