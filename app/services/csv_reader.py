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
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Reglas por prefijo SCIAN (orden interno: se aplana y se ordena por longitud de prefijo descendente).
SCIAN_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    # Combustibles al por menor (SCIAN 46841x); no incluye 468211 autopartes, etc.
    ("gasolineras", ("468411", "468412", "468419")),
    # Gas LP / gaseras (cilindros, tanques estacionarios y similares).
    ("gaseras", ("468413", "468414")),
    # Restaurantes y servicios de preparación de alimentos.
    ("restaurantes", ("722",)),
    # Reciclaje y acopio/recuperación de materiales.
    ("recicladoras", ("56292", "43422", "434311", "434312", "434313")),
    # Almacenamiento especializado para sustancias o materiales de riesgo.
    ("almacen_sustancias_peligrosas", ("49319",)),
    ("museos", ("71211", "71212", "71213", "71219")),
    ("iglesias", ("81321",)),
    ("hospitales", ("622",)),
    ("hoteles", ("721",)),
    ("escuelas", ("611",)),
    ("industria", ("31", "32", "33")),
]

FALLBACK_CATEGORY = "otros"

# Orden fijo para el endpoint de catálogo (todas las categorías que puede devolver la API).
CATEGORY_DISPLAY_ORDER: tuple[str, ...] = (
    "bomberos",
    "policia",
    "almacen_sustancias_peligrosas",
    "recicladoras",
    "restaurantes",
    "gaseras",
    "industria",
    "escuelas",
    "hospitales",
    "hoteles",
    "iglesias",
    "museos",
    "gasolineras",
    "oficinas",
    "otros",
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _scian_prefix_table() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for category, prefixes in SCIAN_CATEGORY_RULES:
        for p in prefixes:
            pairs.append((category, p))
    pairs.sort(key=lambda x: -len(x[1]))
    return pairs


_SCIAN_PREFIX_TABLE: list[tuple[str, str]] = _scian_prefix_table()


def _refine_orden_publico_931412(nom_estab: str, nombre_act: str) -> str:
    """
    931412 agrupa actividades de seguridad y orden público; aquí sí tiene sentido
    usar el nombre para distinguir bomberos / protección civil de policía genérica.
    """
    label = _strip_accents(f"{nom_estab} {nombre_act}".lower())
    if "bombero" in label or "proteccion civil" in label:
        return "bomberos"
    if "policia" in label:
        return "policia"
    return "oficinas"


def _classify_ue(codigo_act: str, nombre_act: str, nom_estab: str) -> str:
    """
    Clasificación por SCIAN (`codigo_act`). No se usa el nombre del establecimiento
    para “adivinar” categoría salvo en códigos ambiguos (p. ej. 931412).
    """
    code = (codigo_act or "").strip()

    if code.startswith("931412"):
        return _refine_orden_publico_931412(nom_estab, nombre_act)

    for category, prefix in _SCIAN_PREFIX_TABLE:
        if code.startswith(prefix):
            return category

    if code.startswith("93141"):
        return "policia"
    if code.startswith("93"):
        return "oficinas"

    return FALLBACK_CATEGORY


def list_supported_categories() -> list[str]:
    """Catálogo estable de categorías simplificadas disponibles en API."""
    return list(CATEGORY_DISPLAY_ORDER)


@dataclass
class Bbox:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


def list_denue_csv_basenames(data_dir: str) -> list[str]:
    """
    Lista archivos `.csv` en `data_dir` (solo nombre de archivo, ordenados).
    Sirve como catálogo de “capas” de datos DENUE en la API.
    """
    p = Path(data_dir)
    if not p.is_dir():
        return []
    names = sorted(
        x.name
        for x in p.iterdir()
        if x.is_file()
        and x.suffix.lower() == ".csv"
        and "diccionario" not in x.name.lower()
    )
    return names


def filter_allowed_basenames(requested: list[str], allowed: list[str]) -> list[str]:
    """Devuelve `requested` ∩ `allowed` (orden de aparición en `requested`)."""
    allow = set(allowed)
    out: list[str] = []
    seen: set[str] = set()
    for x in requested:
        if x in allow and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _peek_csv_columns(filepath: str) -> list[str]:
    """Lee solo la cabecera del CSV para conocer nombres de columnas."""
    common_kwargs: dict = dict(header=0, nrows=0, dtype=str, on_bad_lines="skip")
    for enc in ("utf-8-sig", "latin-1"):
        try:
            peek = pd.read_csv(filepath, encoding=enc, **common_kwargs)
            return peek.columns.tolist()
        except UnicodeDecodeError:
            continue
    peek = pd.read_csv(
        filepath,
        encoding="latin-1",
        encoding_errors="replace",
        **common_kwargs,
    )
    return peek.columns.tolist()


def _usecols_para_denue(cols: list[str]) -> Optional[list[str]]:
    """
    Si el CSV trae cabecera estándar INEGI, solo lee 5 columnas (mucho más rápido).
    Si no, devuelve None y se lee el archivo completo (formato legacy).
    """
    n = len(cols)
    if n < 6:
        return None
    names = (
        "codigo_act",
        "nombre_act",
        "nom_estab",
        "latitud",
        "longitud",
    )
    if all(c in cols for c in names):
        return list(names)
    return None


def _leer_csv(filepath: str, usecols: Optional[list[str]] = None) -> pd.DataFrame:
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
    if usecols is not None:
        common_kwargs["usecols"] = usecols
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
    """Extrae columnas necesarias (sin clasificar aún; eso va al subconjunto final)."""
    cols = df.columns.tolist()
    n = len(cols)
    empty = pd.DataFrame(columns=["lat", "lon", "codigo_act", "nombre_act", "nom_estab"])
    tiene_cabecera_inegi = all(
        c in cols for c in ("latitud", "longitud", "codigo_act", "nombre_act", "nom_estab")
    )
    if not tiene_cabecera_inegi and n < 6:
        return empty

    col_lat = "latitud" if "latitud" in cols else cols[n - 3]
    col_lon = "longitud" if "longitud" in cols else cols[n - 2]
    col_codigo = "codigo_act" if "codigo_act" in cols else cols[4]
    col_nombre = "nombre_act" if "nombre_act" in cols else cols[5]
    col_estab = "nom_estab" if "nom_estab" in cols else cols[2]

    out = df[[col_codigo, col_nombre, col_estab, col_lat, col_lon]].copy()
    out.columns = ["codigo_act", "nombre_act", "nom_estab", "lat", "lon"]
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    out = out.dropna(subset=["lat", "lon"])
    out["codigo_act"] = out["codigo_act"].fillna("").str.strip()
    out["nombre_act"] = out["nombre_act"].fillna("").str.strip()
    out["nom_estab"] = out["nom_estab"].fillna("").str.strip()
    return out


def _agregar_categoria(df: pd.DataFrame) -> pd.DataFrame:
    """Clasificación solo sobre el subconjunto ya filtrado (pocas filas)."""
    out = df.copy()
    out["categoria"] = out.apply(
        lambda r: _classify_ue(
            str(r["codigo_act"]), str(r["nombre_act"]), str(r["nom_estab"])
        ),
        axis=1,
    )
    return out


def filtrar_por_bbox(
    filepath: str,
    bbox: Bbox,
    limit: int,
    prefijos: Optional[list[str]] = None,
    modo_codigos: str = "prefix",
) -> list[dict]:
    """
    Devuelve hasta `limit` registros del CSV que estén dentro del bbox.
    Si se pasan `prefijos`, filtra por `codigo_act` según `modo_codigos`:
      - "prefix": inicia con alguno de los códigos enviados
      - "exact": coincide exactamente con alguno de los códigos enviados
    """
    if not os.path.exists(filepath):
        return []

    header_cols = _peek_csv_columns(filepath)
    usecols = _usecols_para_denue(header_cols)
    df = _leer_csv(filepath, usecols=usecols)
    df = _normalizar(df)

    mask = (
        (df["lat"] >= bbox.min_lat)
        & (df["lat"] <= bbox.max_lat)
        & (df["lon"] >= bbox.min_lon)
        & (df["lon"] <= bbox.max_lon)
    )

    if prefijos:
        codigos = [p.strip() for p in prefijos if p and p.strip()]
        s = df["codigo_act"]
        if modo_codigos == "exact":
            code_mask = s.isin(codigos)
        else:
            code_mask = pd.Series(False, index=df.index)
            for pfx in codigos:
                code_mask = code_mask | s.str.startswith(pfx, na=False)
        mask = mask & code_mask

    masked = df[mask]
    n = len(masked)
    if n <= limit:
        resultado = masked
    elif prefijos is not None:
        # Con filtro por prefijos (p. ej. riesgos/rutas) se mantiene orden estable.
        resultado = masked.head(limit)
    else:
        # Sin prefijos, `head(limit)` devolvía siempre las mismas filas iniciales del CSV
        # (muchas gasolineras/industria) y otras actividades quedaban en 0 en el cliente.
        # Muestra reproducible para mezclar actividades dentro del bbox.
        resultado = masked.sample(n=limit, random_state=42)

    resultado = _agregar_categoria(resultado)
    return resultado[
        ["lat", "lon", "codigo_act", "nombre_act", "nom_estab", "categoria"]
    ].to_dict(
        orient="records"
    )


def filtrar_fuera_bbox_por_categorias(
    filepath: str,
    bbox: Bbox,
    categorias: set[str],
    limit: int,
    prefijos: Optional[list[str]] = None,
    modo_codigos: str = "prefix",
) -> list[dict]:
    """
    Registros del CSV que están **fuera** del bbox y cuya `categoria` está en `categorias`.
    Respeta el mismo filtro por `codigo_act` que `filtrar_por_bbox` cuando `prefijos` no es vacío.
    """
    if not categorias or limit <= 0:
        return []
    if not os.path.exists(filepath):
        return []

    header_cols = _peek_csv_columns(filepath)
    usecols = _usecols_para_denue(header_cols)
    df = _leer_csv(filepath, usecols=usecols)
    df = _normalizar(df)

    mask_inside = (
        (df["lat"] >= bbox.min_lat)
        & (df["lat"] <= bbox.max_lat)
        & (df["lon"] >= bbox.min_lon)
        & (df["lon"] <= bbox.max_lon)
    )
    mask_outside = ~mask_inside

    if prefijos:
        codigos = [p.strip() for p in prefijos if p and p.strip()]
        s = df["codigo_act"]
        if modo_codigos == "exact":
            code_mask = s.isin(codigos)
        else:
            code_mask = pd.Series(False, index=df.index)
            for pfx in codigos:
                code_mask = code_mask | s.str.startswith(pfx, na=False)
        mask_outside = mask_outside & code_mask

    sub = df[mask_outside]
    if len(sub) == 0:
        return []

    sub = _agregar_categoria(sub)
    sub = sub[sub["categoria"].isin(categorias)]
    n = len(sub)
    if n <= limit:
        resultado = sub
    elif prefijos:
        # Misma lógica que `filtrar_por_bbox`: orden estable con filtro SCIAN.
        resultado = sub.head(limit)
    else:
        resultado = sub.sample(n=limit, random_state=42)

    out = resultado[
        ["lat", "lon", "codigo_act", "nombre_act", "nom_estab", "categoria"]
    ].to_dict(orient="records")
    for row in out:
        row["is_exception"] = True
        row["exception_reason"] = "categoria_fuera_bbox"
    return out
