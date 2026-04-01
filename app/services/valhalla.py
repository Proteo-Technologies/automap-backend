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
    body = {
        "locations": [
            {"lon": lon_origen, "lat": lat_origen},
            {"lon": lon_dest, "lat": lat_dest},
        ],
        "costing": "auto",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(VALHALLA_URL, json=body)
        response.raise_for_status()
        data = response.json()

    legs = (data.get("trip") or {}).get("legs") or []
    if not legs or not legs[0].get("shape"):
        raise ValueError("Valhalla no devolvió geometría")

    return decode_polyline6(legs[0]["shape"])
