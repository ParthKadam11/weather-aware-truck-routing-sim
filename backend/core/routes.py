"""Ensure exactly 3 distinct route options; synthesize via-point offsets if needed."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Sequence


@dataclass
class RawRoute:
    """Geometry + timing as returned (or synthesized) from a router."""

    geometry: list[tuple[float, float]]  # (lng, lat)
    distance_m: float
    duration_s: float
    label: str = ""
    via_points: list[tuple[float, float]] = field(default_factory=list)


def _route_signature(route: RawRoute, precision: int = 3) -> tuple:
    """Coarse signature for deduplication (rounded start/mid/end + distance)."""
    coords = route.geometry
    if not coords:
        return (round(route.distance_m, -2),)
    mid = coords[len(coords) // 2]
    return (
        round(coords[0][0], precision),
        round(coords[0][1], precision),
        round(mid[0], precision),
        round(mid[1], precision),
        round(coords[-1][0], precision),
        round(coords[-1][1], precision),
        round(route.distance_m, -3),  # nearest km
    )


def dedupe_routes(routes: Sequence[RawRoute]) -> list[RawRoute]:
    seen: set[tuple] = set()
    unique: list[RawRoute] = []
    for r in routes:
        sig = _route_signature(r)
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(r)
    return unique


def offset_point(
    lng: float,
    lat: float,
    bearing_deg: float,
    distance_km: float,
) -> tuple[float, float]:
    """
    Offset a lat/lng by `distance_km` along `bearing_deg` (0 = north).
    Flat-earth approximation — good enough for via-point nudges (~5–20 km).
    """
    # 1 deg lat ≈ 111.32 km; lng scales with cos(lat)
    dlat = (distance_km * cos(radians(bearing_deg))) / 111.32
    dlng = (distance_km * sin(radians(bearing_deg))) / (111.32 * cos(radians(lat)))
    return (lng + dlng, lat + dlat)


def midpoint(geometry: Sequence[tuple[float, float]]) -> tuple[float, float]:
    if not geometry:
        raise ValueError("empty geometry")
    return geometry[len(geometry) // 2]


def via_point_offsets(
    primary: RawRoute,
    count: int = 2,
    distances_km: Sequence[float] = (12.0, 20.0),
) -> list[tuple[float, float]]:
    """
    Generate via-points perpendicular to the primary route midpoint.

    Alternates left/right of the rough route bearing so OSRM returns
    meaningfully different alternatives when the API gave us fewer than 3.
    """
    if len(primary.geometry) < 2:
        raise ValueError("primary route needs geometry")

    mid_idx = len(primary.geometry) // 2
    lng, lat = primary.geometry[mid_idx]
    # Approximate bearing from a nearby segment
    prev = primary.geometry[max(0, mid_idx - 1)]
    nxt = primary.geometry[min(len(primary.geometry) - 1, mid_idx + 1)]
    dlat = nxt[1] - prev[1]
    dlng = nxt[0] - prev[0]
    bearing = math.degrees(math.atan2(dlng, dlat))

    vias: list[tuple[float, float]] = []
    sides = (90.0, -90.0, 60.0, -60.0, 120.0, -120.0)
    for i in range(count):
        dist = distances_km[i % len(distances_km)]
        bearing_perp = bearing + sides[i % len(sides)]
        vias.append(offset_point(lng, lat, bearing_perp, dist))
    return vias


def ensure_three_routes(
    routes: Sequence[RawRoute],
    *,
    fetch_via_route,
) -> list[RawRoute]:
    """
    Return exactly 3 deduplicated routes.

    `fetch_via_route(via_lng_lat) -> RawRoute | None` is injected so this
    module stays free of HTTP / Django. Caller passes an OSRM wrapper.
    """
    result = dedupe_routes(list(routes))

    if not result:
        raise ValueError("router returned no routes")

    primary = result[0]
    attempt = 0
    # Try several offset distances / angles until we have 3 unique routes
    while len(result) < 3 and attempt < 8:
        need = 3 - len(result)
        vias = via_point_offsets(
            primary,
            count=need,
            distances_km=(10.0 + attempt * 5, 18.0 + attempt * 5),
        )
        for via in vias:
            alt = fetch_via_route(via)
            if alt is None:
                continue
            alt.label = alt.label or f"Alt via offset {attempt}"
            alt.via_points = [via]
            merged = dedupe_routes(result + [alt])
            if len(merged) > len(result):
                result = merged
            if len(result) >= 3:
                break
        attempt += 1

    if len(result) < 3:
        # Last resort: clone primary with tiny synthetic duration/distance
        # jitter so the UI still shows 3 cards (flagged by label).
        while len(result) < 3:
            clone = RawRoute(
                geometry=list(primary.geometry),
                distance_m=primary.distance_m * (1 + 0.01 * len(result)),
                duration_s=primary.duration_s * (1 + 0.01 * len(result)),
                label=f"Variant {len(result) + 1} (limited alternatives)",
            )
            result.append(clone)

    # Label A/B/C
    for i, r in enumerate(result[:3]):
        if not r.label:
            r.label = f"Route {chr(ord('A') + i)}"
    return result[:3]
