"""
Proxy async hacia Valhalla (valhalla1.openstreetmap.de).
Decodifica la polyline precision-6 y devuelve coordenadas [lat, lon].
"""
from __future__ import annotations

import asyncio
import math

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


def _route_signature(coords: list[list[float]]) -> str:
    if not coords:
        return "empty"
    step = max(1, len(coords) // 20)
    sample = coords[::step]
    if sample[-1] != coords[-1]:
        sample.append(coords[-1])
    packed = [f"{round(lat, 5)},{round(lon, 5)}" for lat, lon in sample]
    return f"{len(coords)}|" + "|".join(packed)


def _dedupe_routes(routes: list[list[list[float]]]) -> list[list[list[float]]]:
    out: list[list[list[float]]] = []
    seen: set[str] = set()
    for coords in routes:
        sig = _route_signature(coords)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(coords)
    return out


def _join_routes(
    tramo1: list[list[float]],
    tramo2: list[list[float]],
) -> list[list[float]]:
    if not tramo1:
        return list(tramo2)
    if not tramo2:
        return list(tramo1)
    if tramo1[-1] == tramo2[0]:
        return tramo1 + tramo2[1:]
    return tramo1 + tramo2


def _build_detour_points(
    lat_origen: float,
    lon_origen: float,
    lat_dest: float,
    lon_dest: float,
) -> list[tuple[float, float]]:
    # Puntos de desvío a ambos lados del segmento origen-destino.
    dx = lon_dest - lon_origen
    dy = lat_dest - lat_origen
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return []
    px = -dy / norm
    py = dx / norm
    mid_lon = (lon_origen + lon_dest) / 2.0
    mid_lat = (lat_origen + lat_dest) / 2.0
    # Desvíos moderados (~70m, ~130m, ~210m aprox): evita rodeos exagerados.
    radii = [0.00065, 0.0012, 0.0019]
    points: list[tuple[float, float]] = []
    for r in radii:
        points.append((mid_lat + (py * r), mid_lon + (px * r)))
        points.append((mid_lat - (py * r), mid_lon - (px * r)))
    return points


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _polyline_length_m(coords: list[list[float]]) -> float:
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(coords)):
        total += _haversine_m(
            coords[i - 1][0],
            coords[i - 1][1],
            coords[i][0],
            coords[i][1],
        )
    return total


def _endpoint_error_m(
    coords: list[list[float]],
    lat_dest: float,
    lon_dest: float,
) -> float:
    if not coords:
        return 999999.0
    end = coords[-1]
    return _haversine_m(end[0], end[1], lat_dest, lon_dest)


def _destination_approach_points(lat: float, lon: float) -> list[tuple[float, float]]:
    """
    Puntos alrededor del destino (~60–90 m) para que Valhalla enlace a distintas
    aristas viales y las rutas lleguen por lados distintos.
    """
    out: list[tuple[float, float]] = []
    for meters in (65.0, 95.0):
        dlat = meters / 111_320.0
        dlon = meters / (111_320.0 * math.cos(math.radians(lat)))
        for da, db in (
            (1.0, 0.0),
            (-1.0, 0.0),
            (0.0, 1.0),
            (0.0, -1.0),
            (0.707, 0.707),
            (0.707, -0.707),
            (-0.707, 0.707),
            (-0.707, -0.707),
        ):
            out.append((lat + da * dlat, lon + db * dlon))
    return out


def _polyline_cell_set(coords: list[list[float]], decimals: int = 4) -> set[str]:
    if len(coords) < 2:
        return set()
    step = max(1, len(coords) // 60)
    cells: set[str] = set()
    for i in range(0, len(coords), step):
        lat, lon = coords[i]
        cells.add(f"{round(lat, decimals)},{round(lon, decimals)}")
    cells.add(f"{round(coords[-1][0], decimals)},{round(coords[-1][1], decimals)}")
    return cells


def _dissimilarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return 1.0 - (inter / union) if union else 1.0


def _select_diverse_routes(
    routes: list[list[list[float]]],
    k: int,
) -> list[list[list[float]]]:
    """
    Elige hasta k rutas maximizando diversidad (menos tramos compartidos).
    """
    if not routes or k <= 0:
        return []
    if len(routes) <= k:
        return list(routes)

    cell_sets = [_polyline_cell_set(r) for r in routes]
    lengths = [_polyline_length_m(r) for r in routes]
    order = sorted(range(len(routes)), key=lambda i: lengths[i])

    selected_idx: list[int] = [order[0]]

    while len(selected_idx) < k:
        best_i: int | None = None
        best_mins = -1.0
        best_len = float("inf")
        for i in order:
            if i in selected_idx:
                continue
            mins = min(
                _dissimilarity(cell_sets[i], cell_sets[j]) for j in selected_idx
            )
            if best_i is None or mins > best_mins + 1e-9 or (
                abs(mins - best_mins) <= 1e-9 and lengths[i] < best_len
            ):
                best_i = i
                best_mins = mins
                best_len = lengths[i]
        if best_i is None:
            break
        selected_idx.append(best_i)

    return [routes[i] for i in selected_idx]


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
    locations = [
        {"lon": lon_origen, "lat": lat_origen, "radius": 80},
        {"lon": lon_dest, "lat": lat_dest, "radius": 120},
    ]

    def _mk_body(alternates: int, costing_auto: dict | None = None) -> dict:
        body: dict = {
            "locations": locations,
            "costing": "auto",
            "alternates": max(0, alternates),
        }
        if costing_auto is not None:
            body["costing_options"] = {"auto": costing_auto}
        return body

    # 1) Intento principal: pedir alternativas nativas.
    first_body = _mk_body(alternates=max(0, alt_total - 1))
    # 2) Fallbacks: variar preferencias de costo para inducir trazos distintos.
    fallback_bodies = [
        _mk_body(alternates=0, costing_auto={"use_highways": 1.0, "use_tolls": 1.0}),
        _mk_body(alternates=0, costing_auto={"use_highways": 0.0, "use_tolls": 0.0}),
        _mk_body(alternates=0, costing_auto={"use_highways": 0.2, "use_tolls": 1.0}),
    ]

    def _extract_shapes(data: dict) -> list[str]:
        out: list[str] = []
        main_shape = _extraer_shape(data)
        if main_shape:
            out.append(main_shape)
        for alt in data.get("alternates") or []:
            s = _extraer_shape(alt if isinstance(alt, dict) else {})
            if s:
                out.append(s)
        return out

    unique_shapes: list[str] = []
    seen_shapes: set[str] = set()

    def _append_unique(shapes: list[str]) -> None:
        for s in shapes:
            if s in seen_shapes:
                continue
            seen_shapes.add(s)
            unique_shapes.append(s)

    async def _simple_route(
        client: httpx.AsyncClient,
        lat_a: float,
        lon_a: float,
        lat_b: float,
        lon_b: float,
    ) -> list[list[float]] | None:
        body = {
            "locations": [
                {"lon": lon_a, "lat": lat_a, "radius": 80},
                {"lon": lon_b, "lat": lat_b, "radius": 120},
            ],
            "costing": "auto",
            "alternates": 0,
        }
        try:
            resp = await client.post(VALHALLA_URL, json=body)
            resp.raise_for_status()
            shape = _extraer_shape(resp.json())
            if not shape:
                return None
            return decode_polyline6(shape)
        except httpx.HTTPError:
            return None

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(VALHALLA_URL, json=first_body)
        response.raise_for_status()
        _append_unique(_extract_shapes(response.json()))

        # Si Valhalla devuelve menos alternativas de las pedidas, intentamos variantes.
        if len(unique_shapes) < alt_total:
            for fb in fallback_bodies:
                try:
                    extra_resp = await client.post(VALHALLA_URL, json=fb)
                    extra_resp.raise_for_status()
                    _append_unique(_extract_shapes(extra_resp.json()))
                except httpx.HTTPError:
                    # No rompe flujo principal; solo omite esta variante.
                    continue
                if len(unique_shapes) >= alt_total:
                    break

        # Fallback extra: construir rutas con desvío intermedio.
        if len(unique_shapes) < alt_total and alt_total > 1:
            detours = _build_detour_points(lat_origen, lon_origen, lat_dest, lon_dest)
            # Convertimos lo que ya tenemos a coordenadas para dedup global por geometría.
            current_routes: list[list[list[float]]] = [
                decode_polyline6(s) for s in unique_shapes
            ]
            for via_lat, via_lon in detours:
                tramo_1 = await _simple_route(
                    client, lat_origen, lon_origen, via_lat, via_lon
                )
                tramo_2 = await _simple_route(
                    client, via_lat, via_lon, lat_dest, lon_dest
                )
                if not tramo_1 or not tramo_2:
                    continue
                current_routes.append(_join_routes(tramo_1, tramo_2))
                current_routes = _dedupe_routes(current_routes)
                if len(current_routes) >= alt_total:
                    break
            unique_shapes = []
            # Reconvertimos usando firma derivada de coordenadas.
            seen_coords: set[str] = set()
            for coords in current_routes:
                sig = _route_signature(coords)
                if sig in seen_coords:
                    continue
                seen_coords.add(sig)
                # Guardamos como marcador; no depende de polyline.
                unique_shapes.append(sig)
            routes = _dedupe_routes(current_routes)
        else:
            routes = [decode_polyline6(s) for s in unique_shapes]

        # Llegadas por distintos lados del destino (menos solapamiento entre alternativas).
        if alt_total > 1:
            approach_pts = _destination_approach_points(lat_dest, lon_dest)
            tasks = [
                _simple_route(client, lat_origen, lon_origen, plat, plon)
                for plat, plon in approach_pts[:12]
            ]
            for res in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(res, list) and res and len(res) >= 6:
                    routes.append(res)
            routes = _dedupe_routes(routes)

    if not routes:
        raise ValueError("Valhalla no devolvió geometría")

    # Filtra rutas con rodeos extremos o final demasiado alejado del punto pedido.
    base = min((_polyline_length_m(r) for r in routes if r), default=0.0)
    if base <= 0:
        base = 1.0
    sane_routes: list[list[list[float]]] = []
    for r in routes:
        length = _polyline_length_m(r)
        if length > (base * 1.75):
            continue
        if _endpoint_error_m(r, lat_dest, lon_dest) > 180:
            continue
        sane_routes.append(r)
    if sane_routes:
        routes = _dedupe_routes(sane_routes)

    # Elegir las `alt_total` rutas más diversas (evita dos trazos casi idénticos).
    if len(routes) >= alt_total:
        out = _select_diverse_routes(routes, alt_total)
    else:
        out = list(routes)

    # Contrato operativo: siempre devolver `alt_total`.
    while len(out) < alt_total:
        out.append(list(out[0]))
    return out
