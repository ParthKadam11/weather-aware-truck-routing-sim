"""
Distinct route options from OSRM alternatives + via-point search.

Never clones a route. If only 2 distinct paths exist after search, return 2
and explain why. Geometries are Douglas–Peucker simplified (~50 m) on return.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from math import atan2, cos, degrees, radians, sin
from typing import Callable, Sequence

from core.checkpoints import LatLng, haversine_m

# Overlap / quality thresholds
CELL_DEG = 0.005
OVERLAP_REJECT = 0.8
MAX_DETOUR_RATIO = 1.5
UTURN_TURN_DEG = 155.0
UTURN_MIN_LEG_M = 80.0
SIMPLIFY_TOLERANCE_M = 50.0
VIA_FRACTIONS = (1 / 3, 2 / 3)
VIA_OFFSETS_KM = (15.0, 30.0, 50.0)


@dataclass
class RawRoute:
    """Geometry + timing as returned (or synthesized) from a router."""

    geometry: list[tuple[float, float]]  # (lng, lat)
    distance_m: float
    duration_s: float
    label: str = ""
    via_points: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class RouteSetResult:
    routes: list[RawRoute]
    note: str = ""


def offset_point(
    lng: float,
    lat: float,
    bearing_deg: float,
    distance_km: float,
) -> tuple[float, float]:
    """Offset lat/lng by `distance_km` along `bearing_deg` (0 = north)."""
    dlat = (distance_km * cos(radians(bearing_deg))) / 111.32
    dlng = (distance_km * sin(radians(bearing_deg))) / (
        111.32 * max(0.2, cos(radians(lat)))
    )
    return (lng + dlng, lat + dlat)


def point_at_fraction(
    geometry: Sequence[tuple[float, float]], fraction: float
) -> tuple[float, float]:
    """Point at `fraction` of polyline length (GeoJSON lng/lat)."""
    if len(geometry) < 2:
        raise ValueError("geometry needs 2+ points")
    fraction = max(0.0, min(1.0, fraction))
    points = [LatLng(lat=lat, lng=lng) for lng, lat in geometry]
    total = 0.0
    segs: list[float] = []
    for i in range(len(points) - 1):
        d = haversine_m(points[i], points[i + 1])
        segs.append(d)
        total += d
    if total < 1.0:
        return geometry[len(geometry) // 2]
    target = total * fraction
    walked = 0.0
    for i, d in enumerate(segs):
        if walked + d >= target:
            t = 0.0 if d < 1e-9 else (target - walked) / d
            a, b = geometry[i], geometry[i + 1]
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        walked += d
    return geometry[-1]


def _bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Forward azimuth degrees from A→B (0 = north)."""
    lat1, lat2 = radians(a[1]), radians(b[1])
    dlng = radians(b[0] - a[0])
    x = sin(dlng) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlng)
    return (degrees(atan2(x, y)) + 360.0) % 360.0


def _angle_delta_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def cell_set(
    geometry: Sequence[tuple[float, float]], *, cell_deg: float = CELL_DEG
) -> set[tuple[float, float]]:
    """Snap vertices to a `cell_deg` grid for overlap comparison."""
    if cell_deg <= 0:
        raise ValueError("cell_deg must be positive")
    out: set[tuple[float, float]] = set()
    for lng, lat in geometry:
        out.add(
            (
                round(round(lng / cell_deg) * cell_deg, 6),
                round(round(lat / cell_deg) * cell_deg, 6),
            )
        )
    return out


def overlap_ratio(
    a: Sequence[tuple[float, float]],
    b: Sequence[tuple[float, float]],
    *,
    cell_deg: float = CELL_DEG,
) -> float:
    """|A∩B| / min(|A|,|B|) on snapped cell sets."""
    sa, sb = cell_set(a, cell_deg=cell_deg), cell_set(b, cell_deg=cell_deg)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def has_uturn(
    geometry: Sequence[tuple[float, float]],
    *,
    turn_deg: float = UTURN_TURN_DEG,
    min_leg_m: float = UTURN_MIN_LEG_M,
) -> bool:
    """True if any sharp reverse turn between consecutive legs."""
    if len(geometry) < 3:
        return False
    for i in range(1, len(geometry) - 1):
        a, b, c = geometry[i - 1], geometry[i], geometry[i + 1]
        leg_in = haversine_m(LatLng(a[1], a[0]), LatLng(b[1], b[0]))
        leg_out = haversine_m(LatLng(b[1], b[0]), LatLng(c[1], c[0]))
        if leg_in < min_leg_m or leg_out < min_leg_m:
            continue
        turn = _angle_delta_deg(_bearing_deg(a, b), _bearing_deg(b, c))
        if turn >= turn_deg:
            return True
    return False


def detour_ratio(route: RawRoute, primary: RawRoute) -> float:
    base = max(1.0, primary.distance_m)
    return route.distance_m / base


def is_acceptable_alternative(route: RawRoute, primary: RawRoute) -> bool:
    if len(route.geometry) < 2:
        return False
    if detour_ratio(route, primary) > MAX_DETOUR_RATIO:
        return False
    if has_uturn(route.geometry):
        return False
    return True


def too_similar(
    candidate: RawRoute,
    accepted: Sequence[RawRoute],
    *,
    threshold: float = OVERLAP_REJECT,
) -> bool:
    return any(
        overlap_ratio(candidate.geometry, r.geometry) > threshold for r in accepted
    )


def dedupe_by_overlap(
    routes: Sequence[RawRoute],
    *,
    threshold: float = OVERLAP_REJECT,
) -> list[RawRoute]:
    """Keep routes in order; drop those overlapping an earlier keep > threshold."""
    kept: list[RawRoute] = []
    for r in routes:
        if too_similar(r, kept, threshold=threshold):
            continue
        kept.append(r)
    return kept


def _perpendicular_bearing(geometry: Sequence[tuple[float, float]], fraction: float) -> float:
    """Route bearing near `fraction`, then +90° (one perpendicular)."""
    # Sample a short chord around the fraction point
    f0 = max(0.0, fraction - 0.02)
    f1 = min(1.0, fraction + 0.02)
    a = point_at_fraction(geometry, f0)
    b = point_at_fraction(geometry, f1)
    if a == b and len(geometry) >= 2:
        a, b = geometry[0], geometry[-1]
    return (_bearing_deg(a, b) + 90.0) % 360.0


def via_candidates(
    primary: RawRoute,
    *,
    fractions: Sequence[float] = VIA_FRACTIONS,
    offsets_km: Sequence[float] = VIA_OFFSETS_KM,
) -> list[tuple[float, float]]:
    """
    Via points at 1/3 and 2/3 along the main route, perpendicular at ±15/30/50 km.
    """
    if len(primary.geometry) < 2:
        return []
    out: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for frac in fractions:
        base = point_at_fraction(primary.geometry, frac)
        perp = _perpendicular_bearing(primary.geometry, frac)
        for dist in offsets_km:
            for side in (0.0, 180.0):
                lng, lat = offset_point(base[0], base[1], perp + side, dist)
                key = (round(lng, 5), round(lat, 5))
                if key in seen:
                    continue
                seen.add(key)
                out.append((lng, lat))
    return out


def _point_line_distance_m(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Distance from P to segment AB in meters (local equirectangular)."""
    lat0 = radians(a[1])
    ax = ay = 0.0
    bx = (b[0] - a[0]) * cos(lat0) * 111_320.0
    by = (b[1] - a[1]) * 110_540.0
    px = (p[0] - a[0]) * cos(lat0) * 111_320.0
    py = (p[1] - a[1]) * 110_540.0
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom < 1.0:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * dx + py * dy) / denom))
    return math.hypot(px - t * dx, py - t * dy)


def simplify_geometry(
    geometry: Sequence[tuple[float, float]],
    *,
    tolerance_m: float = SIMPLIFY_TOLERANCE_M,
) -> list[tuple[float, float]]:
    """Douglas–Peucker simplification; tolerance in meters (~50 m default)."""
    coords = list(geometry)
    if len(coords) <= 2:
        return coords

    def _dp(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points
        a, b = points[0], points[-1]
        max_d = -1.0
        idx = 0
        for i in range(1, len(points) - 1):
            d = _point_line_distance_m(points[i], a, b)
            if d > max_d:
                max_d = d
                idx = i
        if max_d > tolerance_m:
            left = _dp(points[: idx + 1])
            right = _dp(points[idx:])
            return left[:-1] + right
        return [a, b]

    return _dp(coords)


def simplify_route(route: RawRoute, *, tolerance_m: float = SIMPLIFY_TOLERANCE_M) -> RawRoute:
    route.geometry = simplify_geometry(route.geometry, tolerance_m=tolerance_m)
    return route


def label_routes(routes: Sequence[RawRoute]) -> list[RawRoute]:
    for i, r in enumerate(routes):
        r.label = f"Route {chr(ord('A') + i)}"
    return list(routes)


FetchViaBatch = Callable[[Sequence[tuple[float, float]]], list[RawRoute | None]]


def ensure_distinct_routes(
    routes: Sequence[RawRoute],
    *,
    fetch_via_batch: FetchViaBatch,
    max_routes: int = 3,
) -> RouteSetResult:
    """
    Prefer OSRM alternatives; if fewer than `max_routes`, search via candidates
    (1/3 & 2/3 × ±15/30/50 km), expecting the caller to snap + fetch in parallel.

    Rejects overlap >0.8, detour >1.5×, and U-turns. Never clones. May return
    fewer than 3 with an explanatory note.
    """
    if not routes:
        raise ValueError("router returned no routes")

    primary = routes[0]
    accepted: list[RawRoute] = [primary]
    for r in routes[1:]:
        if not is_acceptable_alternative(r, primary):
            continue
        if too_similar(r, accepted):
            continue
        accepted.append(r)
        if len(accepted) >= max_routes:
            break

    note = ""
    if len(accepted) < max_routes:
        candidates = via_candidates(accepted[0])
        if candidates:
            fetched = fetch_via_batch(candidates)
            for alt in fetched:
                if alt is None:
                    continue
                if not is_acceptable_alternative(alt, accepted[0]):
                    continue
                if too_similar(alt, accepted):
                    continue
                accepted.append(alt)
                if len(accepted) >= max_routes:
                    break

    if len(accepted) < max_routes:
        note = (
            f"Only {len(accepted)} distinct route"
            f"{'' if len(accepted) == 1 else 's'} available after OSRM "
            f"alternatives and via search (rejected clones, detours >"
            f"{MAX_DETOUR_RATIO:.1f}×, U-turns, and overlaps >{OVERLAP_REJECT})."
        )

    out = [simplify_route(r) for r in accepted[:max_routes]]
    return RouteSetResult(routes=label_routes(out), note=note)


# --- Back-compat aliases used by older tests / call sites ---

def dedupe_routes(routes: Sequence[RawRoute]) -> list[RawRoute]:
    return dedupe_by_overlap(routes)


def via_point_offsets(
    primary: RawRoute,
    count: int = 2,
    distances_km: Sequence[float] = (15.0, 30.0),
) -> list[tuple[float, float]]:
    """Subset of via_candidates for legacy tests."""
    all_vias = via_candidates(primary, offsets_km=tuple(distances_km) or VIA_OFFSETS_KM)
    return all_vias[:count]


def ensure_three_routes(
    routes: Sequence[RawRoute],
    *,
    fetch_via_route,
) -> list[RawRoute]:
    """
    Legacy wrapper: sequential via fetch. Prefer ensure_distinct_routes.
    Does not clone; may return fewer than 3.
    """

    def batch(vias: Sequence[tuple[float, float]]) -> list[RawRoute | None]:
        return [fetch_via_route(v) for v in vias]

    return ensure_distinct_routes(routes, fetch_via_batch=batch).routes
