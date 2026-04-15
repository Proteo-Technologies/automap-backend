"""
Proxy async hacia Valhalla (valhalla1.openstreetmap.de).
Decodifica la polyline precision-6 y devuelve coordenadas [lat, lon].
"""
from __future__ import annotations

import httpx

VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
TIMEOUT_SECONDS = 14


def decode_polyline6(encoded: str) -> list[list[float]]:
    coords: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        shift = result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        shift = result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        coords.append([lat / 1e6, lng / 1e6])
    return coords


async def obtener_ruta(
    lat_origen: float,
    lon_origen: float,
    lat_dest: float,
    lon_dest: float,
) -> list[list[float]]:
    """
    Consulta Valhalla y devuelve lista de coordenadas [[lat, lon], ...].
    Lanza httpx.HTTPError si la petición falla o no contiene geometría.
    """
    rutas = await obtener_rutas(lat_origen, lon_origen, lat_dest, lon_dest, alternativas=1)
    return rutas[0]


def _extraer_shape(payload: dict) -> str | None:
    """
    Extrae la geometría polyline de distintas variantes de respuesta.
    Valhalla puede devolver `shape` dentro de:
    - payload["trip"]["legs"][0]["shape"]
    - payload["legs"][0]["shape"] (en alternates según gateway)
    - payload["shape"] (algunos proxys)
    """
    if not isinstance(payload, dict):
        return None

    direct_shape = payload.get("shape")
    if isinstance(direct_shape, str) and direct_shape:
        return direct_shape

    trip = payload.get("trip")
    if isinstance(trip, dict):
        legs = trip.get("legs") or []
        if legs and isinstance(legs[0], dict):
            shape = legs[0].get("shape")
            if isinstance(shape, str) and shape:
                return shape

    legs = payload.get("legs") or []
    if legs and isinstance(legs[0], dict):
        shape = legs[0].get("shape")
        if isinstance(shape, str) and shape:
            return shape

    return None


async def obtener_rutas(
    lat_origen: float,
    lon_origen: float,
    lat_dest: float,
    lon_dest: float,
    alternativas: int = 1,
) -> list[list[list[float]]]:
    """
    Consulta Valhalla y devuelve una lista de rutas.
    Cada ruta es una lista de coordenadas [[lat, lon], ...].
    """
    alt_total = max(1, min(alternativas, 3))
    body = {
        "locations": [
            {"lon": lon_origen, "lat": lat_origen},
            {"lon": lon_dest, "lat": lat_dest},
        ],
        "costing": "auto",
        # Valhalla interpreta `alternates` como rutas extra además de la principal.
        "alternates": max(0, alt_total - 1),
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(VALHALLA_URL, json=body)
        response.raise_for_status()
        data = response.json()

    shapes: list[str] = []
    main_shape = _extraer_shape(data)
    if main_shape:
        shapes.append(main_shape)

    for alt in data.get("alternates") or []:
        s = _extraer_shape(alt if isinstance(alt, dict) else {})
        if s:
            shapes.append(s)

    if not shapes:
        raise ValueError("Valhalla no devolvió geometría")

    # Mantener orden tal cual entrega el proveedor:
    # principal, alternativa_1, alternativa_2...
    return [decode_polyline6(s) for s in shapes[:alt_total]]
