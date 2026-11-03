"""
Corridor grid: points within a buffer of one or more route polylines.

Coordinates are GeoJSON order throughout: (lng, lat).
"""

from __future__ import annotations

from math import cos, radians
from typing import Sequence

from core.checkpoints import LatLng, haversine_m

# ~30 km weather buffer around routes
DEFAULT_BUFFER_M = 30_000.0
# Grid step ≈ 8 km (balance coverage vs Open-Meteo point count)
DEFAULT_STEP_M = 8_000.0
MAX_GRID_POINTS = 96


def _point_to_segment_m(p: LatLng, a: LatLng, b: LatLng) -> float:
    """Min distance from point P to segment AB (meters)."""
    # Degenerate segment
    ab = haversine_m(a, b)
    if ab < 1.0:
        return haversine_m(p, a)

    # Local equirectangular projection around A for a stable closest-point
    lat0 = radians(a.lat)
    ax, ay = 0.0, 0.0
    bx = (b.lng - a.lng) * cos(lat0) * 111_320.0
    by = (b.lat - a.lat) * 110_540.0
    px = (p.lng - a.lng) * cos(lat0) * 111_320.0
    py = (p.lat - a.lat) * 110_540.0

    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def distance_to_polyline_m(point: tuple[float, float], polyline: Sequence[tuple[float, float]]) -> float:
    """
    Shortest distance from point to polyline.

    `point` and polyline vertices are (lng, lat).
    """
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


def distance_to_any_route_m(
    point: tuple[float, float],
    polylines: Sequence[Sequence[tuple[float, float]]],
) -> float:
    return min(
        (distance_to_polyline_m(point, pl) for pl in polylines if pl),
        default=float("inf"),
    )


def _bbox(
    polylines: Sequence[Sequence[tuple[float, float]]],
    pad_m: float,
) -> tuple[float, float, float, float]:
    """Return (min_lng, min_lat, max_lng, max_lat) with ~pad_m padding."""
    lngs: list[float] = []
    lats: list[float] = []
    for pl in polylines:
        for lng, lat in pl:
            lngs.append(lng)
            lats.append(lat)
    if not lngs:
        raise ValueError("empty polylines")
    mid_lat = sum(lats) / len(lats)
    pad_lat = pad_m / 110_540.0
    pad_lng = pad_m / (111_320.0 * max(0.2, cos(radians(mid_lat))))
    return (
        min(lngs) - pad_lng,
        min(lats) - pad_lat,
        max(lngs) + pad_lng,
        max(lats) + pad_lat,
    )


def corridor_grid_points(
    polylines: Sequence[Sequence[tuple[float, float]]],
    *,
    buffer_m: float = DEFAULT_BUFFER_M,
    step_m: float = DEFAULT_STEP_M,
    max_points: int = MAX_GRID_POINTS,
) -> list[tuple[float, float]]:
    """
    Build a grid of (lng, lat) points within `buffer_m` of any route polyline.

    Returns GeoJSON-ordered coordinates. Caps at `max_points` by coarsening step.
    """
    if not polylines or all(len(p) < 2 for p in polylines):
        raise ValueError("need at least one polyline with 2+ vertices")

    step = step_m
    points: list[tuple[float, float]] = []

    for _ in range(8):
        min_lng, min_lat, max_lng, max_lat = _bbox(polylines, buffer_m)
        mid_lat = (min_lat + max_lat) / 2
        dlat = step / 110_540.0
        dlng = step / (111_320.0 * max(0.2, cos(radians(mid_lat))))

        candidates: list[tuple[float, float]] = []
        lat = min_lat
        while lat <= max_lat + 1e-12:
            lng = min_lng
            while lng <= max_lng + 1e-12:
                pt = (round(lng, 5), round(lat, 5))
                if distance_to_any_route_m(pt, polylines) <= buffer_m:
                    candidates.append(pt)
                lng += dlng
            lat += dlat

        points = candidates
        if len(points) <= max_points:
            break
        step *= 1.35

    if len(points) > max_points:
        # Uniform downsample
        stride = max(1, len(points) // max_points)
        points = points[::stride][:max_points]

    return points
