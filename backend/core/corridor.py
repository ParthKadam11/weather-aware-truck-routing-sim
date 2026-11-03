"""
Corridor sample points along route polylines.

Coordinates are GeoJSON order throughout: (lng, lat).
"""

from __future__ import annotations

from math import cos, hypot, radians
from typing import Sequence

from core.checkpoints import LatLng, haversine_m

# Sample every 8 km along each route
DEFAULT_STEP_M = 8_000.0
# Perpendicular offsets from the centerline
DEFAULT_OFFSETS_M = (10_000.0, 20_000.0)
# Snap / dedupe cell size (~9 km)
DEFAULT_SNAP_DEG = 0.08


def _point_to_segment_m(p: LatLng, a: LatLng, b: LatLng) -> float:
    """Min distance from point P to segment AB (meters)."""
    ab = haversine_m(a, b)
    if ab < 1.0:
        return haversine_m(p, a)

    lat0 = radians(a.lat)
    bx = (b.lng - a.lng) * cos(lat0) * 111_320.0
    by = (b.lat - a.lat) * 110_540.0
    px = (p.lng - a.lng) * cos(lat0) * 111_320.0
    py = (p.lat - a.lat) * 110_540.0

    dx, dy = bx, by
    denom = dx * dx + dy * dy
    t = 0.0 if denom < 1e-12 else ((px * dx + py * dy) / denom)
    t = max(0.0, min(1.0, t))
    qx, qy = t * dx, t * dy
    return hypot(px - qx, py - qy)


def distance_to_polyline_m(
    point: tuple[float, float], polyline: Sequence[tuple[float, float]]
) -> float:
    """Shortest distance from point to polyline. `point` and vertices are (lng, lat)."""
    if len(polyline) < 2:
        if not polyline:
            return float("inf")
        lng, lat = point
        return haversine_m(LatLng(lat, lng), LatLng(polyline[0][1], polyline[0][0]))

    p = LatLng(lat=point[1], lng=point[0])
    best = float("inf")
    for i in range(len(polyline) - 1):
        a = LatLng(lat=polyline[i][1], lng=polyline[i][0])
        b = LatLng(lat=polyline[i + 1][1], lng=polyline[i + 1][0])
        best = min(best, _point_to_segment_m(p, a, b))
    return best


def _snap(lng: float, lat: float, snap_deg: float) -> tuple[float, float]:
    return (
        round(round(lng / snap_deg) * snap_deg, 6),
        round(round(lat / snap_deg) * snap_deg, 6),
    )


def _offset_point(
    lng: float,
    lat: float,
    east_m: float,
    north_m: float,
) -> tuple[float, float]:
    """Displace (lng, lat) by local east/north meters."""
    dlat = north_m / 110_540.0
    dlng = east_m / (111_320.0 * max(0.2, cos(radians(lat))))
    return (lng + dlng, lat + dlat)


def _segment_tangent_en(
    a: tuple[float, float], b: tuple[float, float]
) -> tuple[float, float]:
    """Unit tangent (east_m, north_m) from A→B. Returns (0,0) if degenerate."""
    lng0, lat0 = a
    lng1, lat1 = b
    east = (lng1 - lng0) * cos(radians(lat0)) * 111_320.0
    north = (lat1 - lat0) * 110_540.0
    length = hypot(east, north)
    if length < 1.0:
        return (0.0, 0.0)
    return (east / length, north / length)


def _samples_along_polyline(
    polyline: Sequence[tuple[float, float]],
    step_m: float,
) -> list[tuple[float, float, float, float]]:
    """
    Walk polyline; emit (lng, lat, tang_east, tang_north) at 0, step, 2·step, …

    Always includes the start. Also emits near the end if the last gap ≥ half step.
    """
    if len(polyline) < 2:
        return []

    out: list[tuple[float, float, float, float]] = []
    te, tn = _segment_tangent_en(polyline[0], polyline[1])
    out.append((polyline[0][0], polyline[0][1], te, tn))

    next_at = step_m
    traveled = 0.0

    for i in range(len(polyline) - 1):
        a = LatLng(lat=polyline[i][1], lng=polyline[i][0])
        b = LatLng(lat=polyline[i + 1][1], lng=polyline[i + 1][0])
        seg_m = haversine_m(a, b)
        if seg_m < 1.0:
            continue
        te, tn = _segment_tangent_en(polyline[i], polyline[i + 1])
        while traveled + seg_m >= next_at - 1e-6:
            remain = next_at - traveled
            frac = remain / seg_m
            lng = polyline[i][0] + (polyline[i + 1][0] - polyline[i][0]) * frac
            lat = polyline[i][1] + (polyline[i + 1][1] - polyline[i][1]) * frac
            out.append((lng, lat, te, tn))
            next_at += step_m
        traveled += seg_m

    # Ensure destination vicinity is covered when remainder is meaningful
    end = polyline[-1]
    te, tn = _segment_tangent_en(polyline[-2], polyline[-1])
    if not out or haversine_m(
        LatLng(out[-1][1], out[-1][0]), LatLng(end[1], end[0])
    ) > step_m * 0.5:
        out.append((end[0], end[1], te, tn))

    return out


def corridor_grid_points(
    polylines: Sequence[Sequence[tuple[float, float]]],
    *,
    step_m: float = DEFAULT_STEP_M,
    offsets_m: Sequence[float] = DEFAULT_OFFSETS_M,
    snap_deg: float = DEFAULT_SNAP_DEG,
) -> list[tuple[float, float]]:
    """
    Single pass along each route: centerline every `step_m`, plus perpendicular
    offsets at ± each value in `offsets_m`. Snap to `snap_deg` and dedupe.

    Returns GeoJSON-ordered (lng, lat) points. No max-point cap / coarsening.
    """
    if not polylines or all(len(p) < 2 for p in polylines):
        raise ValueError("need at least one polyline with 2+ vertices")

    seen: set[tuple[float, float]] = set()
    points: list[tuple[float, float]] = []

    lateral = [0.0]
    for off in offsets_m:
        lateral.append(float(off))
        lateral.append(-float(off))

    for pl in polylines:
        if len(pl) < 2:
            continue
        for lng, lat, te, tn in _samples_along_polyline(pl, step_m):
            # Perpendicular unit: rotate tangent 90° (east, north) → (-north, east)
            if hypot(te, tn) < 1e-9:
                pe, pn = 0.0, 1.0
            else:
                pe, pn = -tn, te

            for signed in lateral:
                olng, olat = _offset_point(lng, lat, pe * signed, pn * signed)
                key = _snap(olng, olat, snap_deg)
                if key not in seen:
                    seen.add(key)
                    points.append(key)

    return points
