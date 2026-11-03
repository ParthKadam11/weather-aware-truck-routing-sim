"""Polyline sampling into weather checkpoints every N miles."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from typing import Sequence

from core.units import meters_to_miles, miles_to_meters

ALLOWED_INTERVALS_MI = (10, 25, 50)
EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class LatLng:
    lat: float
    lng: float


@dataclass(frozen=True)
class Checkpoint:
    """A point along the route at a known distance from the origin."""

    index: int
    lat: float
    lng: float
    distance_m: float  # cumulative distance from route start
    segment_m: float  # distance since previous checkpoint (or start)


def haversine_m(a: LatLng, b: LatLng) -> float:
    """Great-circle distance in meters."""
    lat1, lon1 = radians(a.lat), radians(a.lng)
    lat2, lon2 = radians(b.lat), radians(b.lng)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * atan2(sqrt(h), sqrt(1 - h))


def _interpolate(a: LatLng, b: LatLng, fraction: float) -> LatLng:
    """Linear interpolation in lat/lng (fine for short highway segments)."""
    fraction = max(0.0, min(1.0, fraction))
    return LatLng(
        lat=a.lat + (b.lat - a.lat) * fraction,
        lng=a.lng + (b.lng - a.lng) * fraction,
    )


def sample_checkpoints(
    coordinates: Sequence[tuple[float, float]],
    interval_miles: int,
) -> list[Checkpoint]:
    """
    Sample checkpoints every `interval_miles` along a polyline.

    `coordinates` are (lng, lat) — GeoJSON / OSRM order.
    Always includes the origin (index 0) and the destination.
    Raises ValueError if interval is not 10, 25, or 50.
    """
    if interval_miles not in ALLOWED_INTERVALS_MI:
        raise ValueError(
            f"interval_miles must be one of {ALLOWED_INTERVALS_MI}, got {interval_miles}"
        )
    if len(coordinates) < 2:
        raise ValueError("route needs at least 2 coordinates")

    points = [LatLng(lat=lat, lng=lng) for lng, lat in coordinates]
    interval_m = miles_to_meters(interval_miles)

    checkpoints: list[Checkpoint] = [
        Checkpoint(index=0, lat=points[0].lat, lng=points[0].lng, distance_m=0.0, segment_m=0.0)
    ]

    next_target_m = interval_m
    cumulative_m = 0.0

    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        seg_len = haversine_m(a, b)
        if seg_len == 0:
            continue

        while cumulative_m + seg_len >= next_target_m:
            remain = next_target_m - cumulative_m
            frac = remain / seg_len
            pt = _interpolate(a, b, frac)
            prev_dist = checkpoints[-1].distance_m
            checkpoints.append(
                Checkpoint(
                    index=len(checkpoints),
                    lat=pt.lat,
                    lng=pt.lng,
                    distance_m=next_target_m,
                    segment_m=next_target_m - prev_dist,
                )
            )
            next_target_m += interval_m

        cumulative_m += seg_len

    # Always include destination if it isn't already the last checkpoint
    dest = points[-1]
    last = checkpoints[-1]
    if abs(last.lat - dest.lat) > 1e-7 or abs(last.lng - dest.lng) > 1e-7:
        checkpoints.append(
            Checkpoint(
                index=len(checkpoints),
                lat=dest.lat,
                lng=dest.lng,
                distance_m=cumulative_m,
                segment_m=cumulative_m - last.distance_m,
            )
        )
    else:
        # Fix distance on last if we landed exactly on dest via sampling
        checkpoints[-1] = Checkpoint(
            index=last.index,
            lat=dest.lat,
            lng=dest.lng,
            distance_m=cumulative_m,
            segment_m=last.segment_m,
        )

    return checkpoints


def miles(distance_m: float) -> float:
    return meters_to_miles(distance_m)
