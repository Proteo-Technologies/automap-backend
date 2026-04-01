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
    """
    Lee un CSV DENUE y devuelve un DataFrame crudo.

    Los archivos DENUE del INEGI están en Latin-1 / Windows-1252.
    Se intenta primero UTF-8-BOM (por si algún archivo fue re-exportado),
    y en caso de fallo de encoding se reintenta con latin-1, que acepta
    todos los valores de byte (0x00-0xFF) sin excepción.
    """
    common_kwargs: dict = dict(
        header=0,
        dtype=str,
        low_memory=False,
        on_bad_lines="skip",
    )
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(filepath, encoding=enc, **common_kwargs)
        except UnicodeDecodeError:
            continue
    # Último recurso: latin-1 con errors="replace" nunca lanza UnicodeDecodeError
    return pd.read_csv(
        filepath, encoding="latin-1", encoding_errors="replace", **common_kwargs
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
