"""
Proxy async hacia Valhalla (valhalla1.openstreetmap.de).
Decodifica la polyline precision-6 y devuelve coordenadas [lat, lon].
"""
from __future__ import annotations

import asyncio
import itertools
import math

import httpx

VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
VALHALLA_LOCATE_URL = "https://valhalla1.openstreetmap.de/locate"
# Valhalla público puede tardar bajo carga; evita 502 prematuros en alternativas.
TIMEOUT_SECONDS = 30

# Penaliza estacionamientos / service roads que suelen generar “entra y sale” en U.
_VALHALLA_AUTO_COSTING_BASE: dict[str, float | int] = {
    "service_penalty": 26,
    "maneuver_penalty": 8,
}


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


def _build_segment_detour_points(
    lat_origen: float,
    lon_origen: float,
    lat_dest: float,
    lon_dest: float,
) -> list[tuple[float, float]]:
    """
    Desvíos en varios tramos del segmento principal para forzar trazos distintos
    sin rodeos exagerados.
    """
    dx = lon_dest - lon_origen
    dy = lat_dest - lat_origen
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return []

    px = -dy / norm
    py = dx / norm
    points: list[tuple[float, float]] = []

    for t in (0.35, 0.50, 0.65):
        base_lat = lat_origen + (lat_dest - lat_origen) * t
        base_lon = lon_origen + (lon_dest - lon_origen) * t
        for r in (0.00055, 0.0010, 0.0015):
            points.append((base_lat + (py * r), base_lon + (px * r)))
            points.append((base_lat - (py * r), base_lon - (px * r)))

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


def _dedupe_route_signatures(
    routes: list[list[list[float]]],
) -> list[list[list[float]]]:
    """Elimina geometrías con la misma firma muestreada (evita duplicar en el JSON)."""
    seen: set[str] = set()
    out: list[list[list[float]]] = []
    for r in routes:
        sig = _route_signature(r)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(r)
    return out


def _pick_three_min_total_length(
    pool: list[list[list[float]]],
    max_pairwise: float,
) -> list[list[list[float]]] | None:
    """
    Entre las rutas del pool, elige tres cuyos pares no superen `max_pairwise` en
    solapamiento y que minimicen la suma de longitudes (más directas en conjunto).
    """
    if len(pool) < 3:
        return None
    order = sorted(range(len(pool)), key=lambda i: _polyline_length_m(pool[i]))[:18]
    cells = [_polyline_cell_set(pool[i]) for i in order]
    lens = [_polyline_length_m(pool[i]) for i in order]
    m = len(order)
    best: tuple[int, int, int] | None = None
    best_sum = float("inf")
    for ia, ib, ic in itertools.combinations(range(m), 3):
        ca, cb, cc = cells[ia], cells[ib], cells[ic]
        if _shared_ratio(ca, cb) > max_pairwise:
            continue
        if _shared_ratio(ca, cc) > max_pairwise:
            continue
        if _shared_ratio(cb, cc) > max_pairwise:
            continue
        s = lens[ia] + lens[ib] + lens[ic]
        if s < best_sum:
            best_sum = s
            best = (ia, ib, ic)
    if best is None:
        return None
    ia, ib, ic = best
    return [
        [[float(lat), float(lon)] for lat, lon in pool[order[ia]]],
        [[float(lat), float(lon)] for lat, lon in pool[order[ib]]],
        [[float(lat), float(lon)] for lat, lon in pool[order[ic]]],
    ]


def _best_triple_min_max_overlap(
    pool: list[list[list[float]]],
    max_pairwise: float,
) -> list[list[list[float]]] | None:
    """
    Trío de rutas con solapamiento par a par <= `max_pairwise`.
    Entre los válidos minimiza el **máximo** solapamiento (corredores más distintos);
    empate → menor suma de longitudes (más parecido a la referencia visual).
    """
    if len(pool) < 3:
        return None
    order = sorted(range(len(pool)), key=lambda i: _polyline_length_m(pool[i]))[:22]
    cells = [_polyline_cell_set(pool[i]) for i in order]
    lens = [_polyline_length_m(pool[i]) for i in order]
    m = len(order)
    best: tuple[int, int, int] | None = None
    best_key: tuple[float, float] | None = None
    for ia, ib, ic in itertools.combinations(range(m), 3):
        ca, cb, cc = cells[ia], cells[ib], cells[ic]
        o1 = _shared_ratio(ca, cb)
        o2 = _shared_ratio(ca, cc)
        o3 = _shared_ratio(cb, cc)
        mx = max(o1, o2, o3)
        if mx > max_pairwise + 1e-9:
            continue
        s = lens[ia] + lens[ib] + lens[ic]
        key = (mx, s)
        if best is None or best_key is None or key < best_key:
            best_key = key
            best = (ia, ib, ic)
    if best is None:
        return None
    ia, ib, ic = best
    return [
        [[float(lat), float(lon)] for lat, lon in pool[order[ia]]],
        [[float(lat), float(lon)] for lat, lon in pool[order[ib]]],
        [[float(lat), float(lon)] for lat, lon in pool[order[ic]]],
    ]


def _snap_route_end_to_requested_coord(
    coords: list[list[float]],
    lat: float,
    lon: float,
    max_join_m: float = 95.0,
) -> list[list[float]]:
    """
    Todas las alternativas deben terminar en el **mismo** punto pedido (pin).
    Valhalla corta en la calle más cercana; si está cerca, el último vértice pasa
    a ser exactamente `lat`/`lon` (tramo corto implícito pin ↔ calle).
    """
    if not coords:
        return []
    out = [list(p) for p in coords]
    last = out[-1]
    d = _haversine_m(last[0], last[1], lat, lon)
    if 0.3 < d <= max_join_m:
        out[-1] = [float(lat), float(lon)]
    return out


def _urban_short_trip_params(
    direct_seg_m: float,
) -> tuple[float, int, int, bool]:
    """
    Perfil para trayectos cortos: (max_len_factor vs la ruta más corta,
    límite de puntos approach_through, máx. through en desvíos extra,
    ¿permitir expansión en malla densa?).
    Prioridad del producto: **tres geometrías distintas**; se aceptan trayectos
    más largos antes que repetir la misma polyline.
    """
    if direct_seg_m <= 1100:
        return (1.68, 4, 10, True)
    if direct_seg_m <= 1800:
        return (1.62, 6, 10, True)
    if direct_seg_m <= 2500:
        return (1.70, 8, 12, True)
    return (1.75, 10, 16, True)


def _drop_routes_much_longer_than_shortest(
    routes: list[list[list[float]]],
    max_vs_shortest: float,
) -> list[list[list[float]]]:
    """
    Quita rutas que son mucho más largas que la candidata más corta (suele ser
    el efecto de forzar `through` lejos de la línea recta → rodeos enormes).
    """
    if len(routes) < 2 or max_vs_shortest <= 1.0:
        return list(routes)
    lengths = [_polyline_length_m(r) for r in routes]
    m = min(lengths)
    if m <= 1.0:
        return list(routes)
    cap = m * max_vs_shortest
    return [r for i, r in enumerate(routes) if lengths[i] <= cap]


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


def _extract_located_point(payload: dict) -> tuple[float, float] | None:
    """
    Intenta extraer el punto correlacionado a calle desde /locate.
    """
    if not isinstance(payload, dict):
        return None
    edges = payload.get("edges") or []
    if edges and isinstance(edges[0], dict):
        e0 = edges[0]
        clat = e0.get("correlated_lat")
        clon = e0.get("correlated_lon")
        if isinstance(clat, (int, float)) and isinstance(clon, (int, float)):
            return float(clat), float(clon)
    return None


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


def _shared_ratio(a: set[str], b: set[str]) -> float:
    """
    Porcentaje de coincidencia sobre la ruta más corta.
    """
    if not a or not b:
        return 0.0
    inter = len(a & b)
    base = min(len(a), len(b))
    return (inter / base) if base else 0.0


def _is_loopy_route(coords: list[list[float]]) -> bool:
    """
    Heurística anti-círculos:
    - muchas celdas repetidas en toda la ruta
    - exceso de vueltas cerca del destino al final
    """
    if len(coords) < 10:
        return False

    visited: dict[str, int] = {}
    for lat, lon in coords:
        key = f"{round(lat, 5)},{round(lon, 5)}"
        visited[key] = visited.get(key, 0) + 1
    repeated = sum(c - 1 for c in visited.values() if c > 1)
    if repeated / len(coords) > 0.18:
        return True

    end_lat, end_lon = coords[-1]
    tail = coords[max(0, len(coords) - (len(coords) // 3)) :]
    near_dest = 0
    for lat, lon in tail:
        if _haversine_m(lat, lon, end_lat, end_lon) <= 120:
            near_dest += 1
    if tail and (near_dest / len(tail)) > 0.72:
        return True

    return False


def _bearing_rad(a: list[float], b: list[float]) -> float:
    """Rumbo inicial geográfico de a → b (radianes)."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        dlon
    )
    return math.atan2(y, x)


def _abs_bearing_diff_rad(b1: float, b2: float) -> float:
    d = abs(b1 - b2)
    if d > math.pi:
        d = 2 * math.pi - d
    return d


def _route_has_suspicious_backtrack(coords: list[list[float]]) -> bool:
    """
    Detecta yo-yo: dos puntos del trazo muy cercanos en línea recta pero separados
    por muchos vértices y mucha longitud de vía (baja y regresa por el mismo corredor).
    """
    n = len(coords)
    if n < 10:
        return False
    stride = max(1, n // 100)
    for i in range(0, n - 8, stride):
        for dj in (10, 14, 18, 22, 28, 36, 48, 64, 80, 100):
            j = i + dj
            if j >= n:
                break
            chord = _haversine_m(
                coords[i][0], coords[i][1], coords[j][0], coords[j][1]
            )
            plen = _polyline_length_m(coords[i : j + 1])
            if chord <= 22 and plen >= max(75.0, chord * 3.2):
                return True
            if chord <= 42 and plen >= max(140.0, chord * 3.8):
                return True
    return False


def _route_hairpin_u_turn(coords: list[list[float]]) -> bool:
    """
    Tramo de tres vértices donde A y C quedan cerca pero se recorre mucho más
    que la cuerda y el giro es muy cerrado (garaje, estacionamiento, U).
    """
    n = len(coords)
    if n < 4:
        return False
    for i in range(0, n - 2):
        a, b, c = coords[i], coords[i + 1], coords[i + 2]
        d_ab = _haversine_m(a[0], a[1], b[0], b[1])
        d_bc = _haversine_m(b[0], b[1], c[0], c[1])
        d_ac = _haversine_m(a[0], a[1], c[0], c[1])
        if d_ac > 95 or d_ab < 3 or d_bc < 3:
            continue
        if d_ab + d_bc < 3.0 * max(d_ac, 12.0):
            continue
        if _abs_bearing_diff_rad(_bearing_rad(a, b), _bearing_rad(b, c)) > math.radians(
            118
        ):
            return True
    return False


def _route_terminal_hook(coords: list[list[float]]) -> bool:
    """Gancho corto cerca del destino: rectángulo / zig innecesario en el último tramo."""
    n = len(coords)
    if n < 14:
        return False
    t0 = max(0, int(n * 0.62))
    stride = max(1, (n - t0) // 30)
    for i in range(t0, n - 6, stride):
        for dj in (7, 10, 14, 18, 24, 32):
            j = i + dj
            if j >= n:
                break
            chord = _haversine_m(
                coords[i][0], coords[i][1], coords[j][0], coords[j][1]
            )
            plen = _polyline_length_m(coords[i : j + 1])
            if chord <= 36 and plen >= max(88.0, chord * 3.0):
                return True
    return False


def _route_has_wasteful_local_geometry(coords: list[list[float]]) -> bool:
    return (
        _route_has_suspicious_backtrack(coords)
        or _route_hairpin_u_turn(coords)
        or _route_terminal_hook(coords)
    )


def _route_geometry_unacceptable(coords: list[list[float]]) -> bool:
    """True si la polyline no debería ofrecerse como alternativa razonable."""
    return _is_loopy_route(coords) or _route_has_wasteful_local_geometry(coords)


def _pick_routes_with_overlap_limit(
    routes: list[list[list[float]]],
    k: int,
    max_shared: float,
) -> list[list[list[float]]]:
    if not routes or k <= 0:
        return []
    if len(routes) <= k:
        return list(routes)

    cell_sets = [_polyline_cell_set(r) for r in routes]
    lengths = [_polyline_length_m(r) for r in routes]
    order = sorted(range(len(routes)), key=lambda i: lengths[i])

    selected_idx: list[int] = []
    for idx in order:
        if not selected_idx:
            selected_idx.append(idx)
            continue
        can_add = True
        for j in selected_idx:
            if _shared_ratio(cell_sets[idx], cell_sets[j]) > max_shared:
                can_add = False
                break
        if can_add:
            selected_idx.append(idx)
        if len(selected_idx) == k:
            break

    return [routes[i] for i in selected_idx]


def _dedupe_near_identical_routes(
    routes: list[list[list[float]]],
    max_shared: float = 0.92,
) -> list[list[list[float]]]:
    """
    Elimina rutas visualmente casi idénticas.
    Conserva primero las más cortas.
    """
    if len(routes) <= 1:
        return list(routes)
    order = sorted(range(len(routes)), key=lambda i: _polyline_length_m(routes[i]))
    cell_sets = [_polyline_cell_set(r) for r in routes]
    keep: list[int] = []
    for idx in order:
        if not keep:
            keep.append(idx)
            continue
        too_similar = False
        for j in keep:
            if _shared_ratio(cell_sets[idx], cell_sets[j]) >= max_shared:
                too_similar = True
                break
        if not too_similar:
            keep.append(idx)
    return [routes[i] for i in keep]


def _fill_with_distinct_geometries(
    selected: list[list[list[float]]],
    pool: list[list[list[float]]],
    k: int,
) -> list[list[list[float]]]:
    """
    Completa hasta k rutas sin repetir la misma geometría (firma muestreada).
    Nunca duplica la primera ruta para “cumplir número”: eso hace que el
    frontend muestre una sola línea aunque vengan 3 objetos en JSON.
    """
    if k <= 0:
        return []
    out: list[list[list[float]]] = [[list(p) for p in r] for r in selected]
    seen: set[str] = {_route_signature(r) for r in out}
    for r in pool:
        if len(out) >= k:
            break
        sig = _route_signature(r)
        if sig in seen:
            continue
        seen.add(sig)
        out.append([[float(lat), float(lon)] for lat, lon in r])
    return out[:k]


def _greedy_add_by_dissimilarity(
    selected: list[list[list[float]]],
    pool: list[list[list[float]]],
    k: int,
) -> list[list[list[float]]]:
    """
    Añade rutas cuya firma aún no está en `selected`, priorizando la que maximiza
    la disimilitud mínima frente a las ya elegidas (útil para una 3.ª línea
    claramente distinta aunque comparta >30% con la primera en trayectos cortos).
    """
    if k <= 0:
        return []
    if not selected:
        return []
    out: list[list[list[float]]] = [[list(p) for p in r] for r in selected]
    seen: set[str] = {_route_signature(r) for r in out}
    cell_sets_sel = [_polyline_cell_set(r) for r in out]
    while len(out) < k:
        if not cell_sets_sel:
            break
        best_r: list[list[float]] | None = None
        best_score = -1.0
        for r in pool:
            sig = _route_signature(r)
            if sig in seen:
                continue
            c = _polyline_cell_set(r)
            score = min(_dissimilarity(c, s) for s in cell_sets_sel)
            if score > best_score + 1e-9:
                best_score = score
                best_r = r
        if best_r is None:
            break
        seen.add(_route_signature(best_r))
        out.append([[float(lat), float(lon)] for lat, lon in best_r])
        cell_sets_sel.append(_polyline_cell_set(best_r))
    return out[:k]


def _select_pairwise_overlap_limited(
    candidates: list[list[list[float]]],
    k: int,
    max_pairwise: float,
) -> list[list[list[float]]]:
    """
    Elige hasta k rutas (prefiriendo las más cortas) de forma que cada par
    comparta como máximo `max_pairwise` del recorrido del más corto del par.
    """
    if not candidates or k <= 0:
        return []
    order = sorted(range(len(candidates)), key=lambda i: _polyline_length_m(candidates[i]))
    picked: list[list[list[float]]] = []
    picked_cells: list[set[str]] = []
    for i in order:
        c = _polyline_cell_set(candidates[i])
        if all(_shared_ratio(c, pc) <= max_pairwise for pc in picked_cells):
            picked.append([[float(lat), float(lon)] for lat, lon in candidates[i]])
            picked_cells.append(c)
        if len(picked) == k:
            break
    return picked


def _build_dense_short_trip_detours(
    lat_origen: float,
    lon_origen: float,
    lat_dest: float,
    lon_dest: float,
    scale: float = 1.0,
) -> list[tuple[float, float]]:
    """
    Malla de puntos vía para trayectos cortos: más densidad que
    _build_segment_detour_points + _build_detour_points solos.
    """
    dx = lon_dest - lon_origen
    dy = lat_dest - lat_origen
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return []
    px = -dy / norm
    py = dx / norm
    points: list[tuple[float, float]] = []
    radii = [0.00035, 0.0005, 0.0007, 0.0009, 0.00115, 0.00145, 0.0018]
    radii = [r * scale for r in radii]
    for t in (0.22, 0.28, 0.35, 0.42, 0.5, 0.58, 0.65, 0.72, 0.78):
        base_lat = lat_origen + (lat_dest - lat_origen) * t
        base_lon = lon_origen + (lon_dest - lon_origen) * t
        for r in radii:
            points.append((base_lat + (py * r), base_lon + (px * r)))
            points.append((base_lat - (py * r), base_lon - (px * r)))
    return points


async def _nearest_street_point(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
) -> tuple[float, float]:
    """
    Obtiene la calle más cercana al punto solicitado. Si falla, regresa el punto original.
    """
    body = {"locations": [{"lat": lat, "lon": lon}]}
    try:
        resp = await client.post(VALHALLA_LOCATE_URL, json=body)
        resp.raise_for_status()
        located = _extract_located_point(resp.json())
        if located:
            return located
    except httpx.HTTPError:
        pass
    return lat, lon


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
        auto_opts: dict[str, float | int] = dict(_VALHALLA_AUTO_COSTING_BASE)
        if costing_auto:
            auto_opts.update(costing_auto)
        return {
            "locations": locations,
            "costing": "auto",
            "alternates": max(0, alternates),
            "costing_options": {"auto": auto_opts},
        }

    # Se inicializan aquí y se recalculan tras correlacionar destino a calle.
    first_body = _mk_body(alternates=max(0, alt_total - 1))
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
            "costing_options": {"auto": dict(_VALHALLA_AUTO_COSTING_BASE)},
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

    async def _route_through(
        client: httpx.AsyncClient,
        lat_o: float,
        lon_o: float,
        lat_via: float,
        lon_via: float,
        lat_d: float,
        lon_d: float,
    ) -> list[list[float]] | None:
        """
        Una sola petición origen → punto vía (through) → destino.
        Evita duplicar llamadas (origen-vía + vía-destino) y acelera trayectos cortos.
        """
        body = {
            "locations": [
                {"lon": lon_o, "lat": lat_o, "radius": 80},
                {
                    "lon": lon_via,
                    "lat": lat_via,
                    "radius": 70,
                    "type": "through",
                },
                {"lon": lon_d, "lat": lat_d, "radius": 120},
            ],
            "costing": "auto",
            "alternates": 0,
            "costing_options": {"auto": dict(_VALHALLA_AUTO_COSTING_BASE)},
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
        _valhalla_sem = asyncio.Semaphore(12)

        async def _through_limited(
            lat_o: float,
            lon_o: float,
            lat_via: float,
            lon_via: float,
            lat_d: float,
            lon_d: float,
        ) -> list[list[float]] | None:
            async with _valhalla_sem:
                return await _route_through(
                    client, lat_o, lon_o, lat_via, lon_via, lat_d, lon_d
                )

        # Primero correlaciona destino con la calle más cercana.
        snapped_dest_lat, snapped_dest_lon = await _nearest_street_point(
            client, lat_dest, lon_dest
        )
        locations = [
            {"lon": lon_origen, "lat": lat_origen, "radius": 80},
            {"lon": snapped_dest_lon, "lat": snapped_dest_lat, "radius": 120},
        ]
        direct_seg_m = _haversine_m(
            lat_origen, lon_origen, snapped_dest_lat, snapped_dest_lon
        )
        # Recalcula cuerpos para usar destino correlacionado (calle más cercana).
        first_body = _mk_body(alternates=max(0, alt_total - 1))
        fallback_bodies = [
            _mk_body(
                alternates=0,
                costing_auto={"use_highways": 1.0, "use_tolls": 1.0},
            ),
            _mk_body(
                alternates=0,
                costing_auto={"use_highways": 0.0, "use_tolls": 0.0},
            ),
            _mk_body(
                alternates=0,
                costing_auto={"use_highways": 0.2, "use_tolls": 1.0},
            ),
        ]

        response = await client.post(VALHALLA_URL, json=first_body)
        response.raise_for_status()
        _append_unique(_extract_shapes(response.json()))

        # Si Valhalla devuelve menos alternativas de las pedidas, intentamos variantes
        # en paralelo (antes en serie sumaban mucha latencia).
        if len(unique_shapes) < alt_total:

            async def _post_route_body(body: dict) -> list[str]:
                try:
                    extra_resp = await client.post(VALHALLA_URL, json=body)
                    extra_resp.raise_for_status()
                    return _extract_shapes(extra_resp.json())
                except httpx.HTTPError:
                    return []

            for shapes in await asyncio.gather(
                *(_post_route_body(fb) for fb in fallback_bodies)
            ):
                _append_unique(shapes)

        # Fallback extra: construir rutas con desvío intermedio.
        if len(unique_shapes) < alt_total and alt_total > 1:
            detours = _build_detour_points(
                lat_origen, lon_origen, snapped_dest_lat, snapped_dest_lon
            ) + _build_segment_detour_points(
                lat_origen, lon_origen, snapped_dest_lat, snapped_dest_lon
            )
            # Convertimos lo que ya tenemos a coordenadas para dedup global por geometría.
            current_routes: list[list[list[float]]] = [
                decode_polyline6(s) for s in unique_shapes
            ]
            detour_tasks = [
                _through_limited(
                    lat_origen,
                    lon_origen,
                    via_lat,
                    via_lon,
                    snapped_dest_lat,
                    snapped_dest_lon,
                )
                for via_lat, via_lon in detours[:6]
            ]
            for res in await asyncio.gather(*detour_tasks, return_exceptions=True):
                if isinstance(res, list) and res and len(res) >= 4:
                    current_routes.append(res)
                    current_routes = _dedupe_routes(current_routes)
                    if len(current_routes) >= alt_total + 4:
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

        # Llegadas por distintos lados del destino: en trayectos muy cortos esto
        # fuerza demasiado “ir primero al lado del destino” y aparecen ganchos enormes.
        _, approach_lim, extra_cap, allow_dense = _urban_short_trip_params(direct_seg_m)

        def _n_distinct_sigs(rs: list[list[list[float]]]) -> int:
            return len({_route_signature(r) for r in rs})

        if alt_total > 1 and approach_lim > 0 and _n_distinct_sigs(routes) < 5:
            approach_pts = _destination_approach_points(
                snapped_dest_lat, snapped_dest_lon
            )
            tasks = [
                _through_limited(
                    lat_origen,
                    lon_origen,
                    plat,
                    plon,
                    snapped_dest_lat,
                    snapped_dest_lon,
                )
                for plat, plon in approach_pts[:approach_lim]
            ]
            for res in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(res, list) and res and len(res) >= 6:
                    routes.append(res)
            routes = _dedupe_routes(routes)

        # Trayectos cortos: pocos desvíos ligeros (sin malla densa) para alternativas
        # sin obligar a Valhalla a dar la vuelta a manzanas enteras.
        if alt_total > 1 and direct_seg_m <= 2500 and _n_distinct_sigs(routes) < 5:
            extra_detours = _build_segment_detour_points(
                lat_origen, lon_origen, snapped_dest_lat, snapped_dest_lon
            ) + _build_detour_points(
                lat_origen, lon_origen, snapped_dest_lat, snapped_dest_lon
            )
            extra_tasks = [
                _through_limited(
                    lat_origen,
                    lon_origen,
                    via_lat,
                    via_lon,
                    snapped_dest_lat,
                    snapped_dest_lon,
                )
                for via_lat, via_lon in extra_detours[:extra_cap]
            ]
            for res in await asyncio.gather(*extra_tasks, return_exceptions=True):
                if isinstance(res, list) and res and len(res) >= 4:
                    routes.append(res)
            routes = _dedupe_routes(routes)
            if allow_dense and _n_distinct_sigs(routes) < 3:
                grid = _build_dense_short_trip_detours(
                    lat_origen,
                    lon_origen,
                    snapped_dest_lat,
                    snapped_dest_lon,
                    scale=1.05,
                )
                grid_n = 8 if direct_seg_m <= 1400 else 10
                grid_tasks = [
                    _through_limited(
                        lat_origen,
                        lon_origen,
                        via_lat,
                        via_lon,
                        snapped_dest_lat,
                        snapped_dest_lon,
                    )
                    for via_lat, via_lon in grid[:grid_n]
                ]
                for res in await asyncio.gather(*grid_tasks, return_exceptions=True):
                    if isinstance(res, list) and res and len(res) >= 4:
                        routes.append(res)
                routes = _dedupe_routes(routes)

    if not routes:
        raise ValueError("Valhalla no devolvió geometría")

    direct_trip_m = _haversine_m(lat_origen, lon_origen, lat_dest, lon_dest)
    routes_pre_stretch = _dedupe_routes(list(routes))
    # Solo si hay varios candidatos: quita rutas muy largas vs. la más corta (through lejanos).
    # Umbrales algo más laxos si no sobran firmas: prioridad = ≥3 geometrías distintas.
    if alt_total > 1 and direct_trip_m <= 2500 and len(routes) >= 4:
        if direct_trip_m <= 1200:
            stretches = (1.38, 1.52, 1.68, 1.85)
        elif direct_trip_m <= 1800:
            stretches = (1.42, 1.56, 1.72, 1.88)
        else:
            stretches = (1.48, 1.62, 1.78, 1.92)
        last_s = stretches[-1]
        for stretch in stretches:
            pruned = _drop_routes_much_longer_than_shortest(routes, stretch)
            sigs = len({_route_signature(r) for r in pruned})
            if len(pruned) >= alt_total + 2 and sigs >= alt_total + 1:
                routes = pruned
                break
            if stretch >= last_s - 1e-9:
                routes = pruned
                break
        routes = _dedupe_routes(routes)

    # Filtra rutas con rodeos extremos, círculos o final demasiado alejado del punto pedido.
    max_len_factor = (
        _urban_short_trip_params(direct_trip_m)[0] if direct_trip_m <= 2500 else 1.75
    )
    routes_pre_sane = _dedupe_routes(list(routes))
    base = min((_polyline_length_m(r) for r in routes_pre_sane if r), default=0.0)
    if base <= 0:
        base = 1.0
    sane_routes: list[list[list[float]]] = []
    for r in routes_pre_sane:
        length = _polyline_length_m(r)
        if length > (base * max_len_factor):
            continue
        if _route_geometry_unacceptable(r):
            continue
        if _endpoint_error_m(r, lat_dest, lon_dest) > 180:
            continue
        sane_routes.append(r)
    if sane_routes:
        routes = _dedupe_routes(sane_routes)
    else:
        routes = list(routes_pre_sane)

    # Pool para relleno y elección de trío: rutas “preferidas” (cortas) + candidatas más largas
    # pero aún válidas (sin bucles, destino razonable), para no quedarse con una sola firma.
    pool_len_tolerant = [
        r
        for r in routes_pre_sane
        if not _route_geometry_unacceptable(r)
        and _endpoint_error_m(r, lat_dest, lon_dest) <= 180
    ]
    pool_for_fill = _dedupe_route_signatures(
        [[[float(lat), float(lon)] for lat, lon in r] for r in routes]
        + [[[float(lat), float(lon)] for lat, lon in r] for r in pool_len_tolerant]
    )
    # Si el podado por stretch dejó pocas variantes, recupera firmas del pool previo.
    if len({_route_signature(r) for r in pool_for_fill}) < alt_total + 1:
        pool_for_fill = _dedupe_route_signatures(
            pool_for_fill
            + [
                [[float(lat), float(lon)] for lat, lon in r]
                for r in routes_pre_stretch
                if not _route_geometry_unacceptable(r)
                and _endpoint_error_m(r, lat_dest, lon_dest) <= 180
            ]
        )

    is_short_trip = direct_trip_m <= 2500
    # Bastante estricto: evita dos “alternativas” casi la misma antes de elegir el trío.
    near_identical_max = 0.70 if is_short_trip else 0.88
    routes_before_near = [
        [[float(lat), float(lon)] for lat, lon in r] for r in routes
    ]
    routes = _dedupe_near_identical_routes(routes, max_shared=near_identical_max)
    if not routes and routes_before_near:
        routes = [list(map(list, r)) for r in routes_before_near]

    # Prioriza rutas con poco solapamiento; no relajar demasiado (≤30% es objetivo de producto).
    out = _pick_routes_with_overlap_limit(routes, alt_total, max_shared=0.30)
    if len(out) < alt_total:
        for relaxed in (0.34, 0.38, 0.42, 0.46, 0.50, 0.52):
            out = _pick_routes_with_overlap_limit(routes, alt_total, max_shared=relaxed)
            if len(out) >= alt_total:
                break
    if len(out) < alt_total:
        out = _select_diverse_routes(routes, alt_total)

    # Nunca repetir la misma geometría 2–3 veces: el mapa mostraría una sola línea.
    out = _fill_with_distinct_geometries(out, pool_for_fill, alt_total)
    if len(out) < alt_total:
        out = _fill_with_distinct_geometries(out, routes, alt_total)
    if len(out) < alt_total:
        out = _greedy_add_by_dissimilarity(out, pool_for_fill, alt_total)

    # Tres alternativas: primero trío con **menor solapamiento máximo** (corredores distintos);
    # si no hay, suma mínima de longitudes; último recurso, solapamiento algo mayor.
    best_pw: list[list[list[float]]] = list(out)
    if alt_total == 3 and len(pool_for_fill) >= 3:
        triple: list[list[list[float]]] | None = None
        for max_pw in (0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.42, 0.46, 0.50):
            triple = _best_triple_min_max_overlap(pool_for_fill, max_pw)
            if triple is not None:
                best_pw = triple
                break
        if triple is None:
            for max_pw in (0.34, 0.40, 0.46, 0.52, 0.58, 0.64, 0.72):
                triple = _pick_three_min_total_length(pool_for_fill, max_pw)
                if triple is not None:
                    best_pw = triple
                    break
        if triple is None:
            for max_pw in (0.38, 0.44, 0.50, 0.56, 0.62, 0.68):
                cand = _select_pairwise_overlap_limited(pool_for_fill, alt_total, max_pw)
                if len(cand) >= alt_total:
                    best_pw = cand
                    break
        out = best_pw
    else:
        for max_pw in (0.38, 0.44, 0.50, 0.56, 0.62, 0.68):
            cand = _select_pairwise_overlap_limited(pool_for_fill, alt_total, max_pw)
            if len(cand) >= alt_total:
                best_pw = cand
                break
        out = best_pw

    # Quitar duplicados exactos por firma; rellenar desde un pool amplio (incl. rutas más largas).
    out = _dedupe_route_signatures(out)
    alt_pool = _dedupe_route_signatures(
        pool_for_fill
        + [
            [[float(lat), float(lon)] for lat, lon in r]
            for r in routes_pre_sane
            if not _route_geometry_unacceptable(r)
            and _endpoint_error_m(r, lat_dest, lon_dest) <= 220
        ]
    )
    if len(out) < alt_total:
        out = _fill_with_distinct_geometries(out, alt_pool, alt_total)
    if len(out) < alt_total:
        out = _greedy_add_by_dissimilarity(out, alt_pool, alt_total)
    if len(out) < alt_total:
        for max_pw in (0.52, 0.58, 0.64):
            trip = (
                _best_triple_min_max_overlap(alt_pool, max_pw)
                if alt_total == 3
                else None
            )
            if trip is not None:
                out = trip
                break
        if len(out) < alt_total and alt_total == 3:
            cand = _select_pairwise_overlap_limited(alt_pool, alt_total, 0.68)
            if len(cand) >= alt_total:
                out = cand

    out = out[:alt_total]
    # Mismo punto final exacto que el pin (coordenadas solicitadas).
    pool_snapped = _dedupe_route_signatures(
        [
            _snap_route_end_to_requested_coord(
                [[float(lat), float(lon)] for lat, lon in r],
                lat_dest,
                lon_dest,
            )
            for r in alt_pool
        ]
    )
    out = [
        _snap_route_end_to_requested_coord(list(map(list, r)), lat_dest, lon_dest)
        for r in out
    ]
    out = _dedupe_route_signatures(out)
    if len(out) < alt_total:
        out = _fill_with_distinct_geometries(out, pool_snapped, alt_total)
    if len(out) < alt_total:
        out = _greedy_add_by_dissimilarity(out, pool_snapped, alt_total)

    # Contrato: `alt_total` entradas; duplicar solo si no hay más firmas distintas tras el snap.
    while len(out) < alt_total:
        if not out:
            raise ValueError("Valhalla no devolvió rutas válidas")
        out.append([list(p) for p in out[-1]])

    return out[:alt_total]
