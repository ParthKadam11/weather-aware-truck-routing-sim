"""
Demo storm overlay — one StormConfig shared by analyze checkpoints and heatmap.

Radius is small (~0.3°) and the center sits *beside* one route midpoint so
typically 1–2 of the three alternatives are hit, not all three.
Wind + rain only; snow is left untouched; no minimum floors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class StormConfig:
    lat: float
    lng: float
    radius_deg: float = 0.3
    """Gaussian peak index on the forecast axis (hour 0 = current UTC hour)."""
    peak_hour: int = 2
    wind_boost_mph: float = 55.0
    rain_boost_in: float = 1.15
    """Hours after departure hour for the peak (clamped to 1–2)."""
    peak_offset_h: int = 2


def _midpoint(polyline: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """GeoJSON (lng, lat) midpoint vertex."""
    if not polyline:
        raise ValueError("empty polyline")
    return polyline[len(polyline) // 2]


def _perp_offset_deg(
    polyline: Sequence[tuple[float, float]],
    *,
    offset_deg: float = 0.15,
) -> tuple[float, float]:
    """
    Point beside the route midpoint, offset ~offset_deg along a local perpendicular.

    Keeps the storm center off the corridor centerline so distant alternatives
    fall outside the 0.3° radius.
    """
    lng, lat = _midpoint(polyline)
    if len(polyline) < 2:
        return (lng + offset_deg, lat)

    mid_i = len(polyline) // 2
    a = polyline[max(0, mid_i - 1)]
    b = polyline[min(len(polyline) - 1, mid_i + 1)]
    # Local east/north in degrees (approx)
    east = (b[0] - a[0]) * max(0.2, math.cos(math.radians(lat)))
    north = b[1] - a[1]
    length = math.hypot(east, north)
    if length < 1e-9:
        return (lng + offset_deg, lat)
    # Perpendicular unit in deg-space
    pe, pn = -north / length, east / length
    return (lng + pe * offset_deg, lat + pn * offset_deg)


def departure_hour_index(times: Sequence[str], departure_utc: datetime) -> int:
    """Index of the forecast slot nearest to departure (UTC hourly)."""
    if not times:
        return 0
    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=timezone.utc)
    target = departure_utc.astimezone(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    target_str = target.strftime("%Y-%m-%dT%H:%M")
    if target_str in times:
        return list(times).index(target_str)
    best_i, best_d = 0, float("inf")
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        d = abs((dt - target).total_seconds())
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def build_storm_config(
    polylines: Sequence[Sequence[tuple[float, float]]],
    *,
    departure_utc: datetime,
    forecast_times: Sequence[str],
    peak_offset_h: int = 2,
    radius_deg: float = 0.3,
) -> StormConfig:
    """
    Build the shared storm used by analyze + heatmap.

    Centers beside route A's midpoint; peak is 1–2h after departure on the
    forecast axis (hour 0 = current UTC hour).
    """
    if not polylines:
        raise ValueError("need at least one route polyline")
    # Prefer the first (primary) route so offsets leave the farthest alt clear
    primary = next((pl for pl in polylines if len(pl) >= 2), None)
    if primary is None:
        raise ValueError("need a polyline with 2+ vertices")

    lng, lat = _perp_offset_deg(primary, offset_deg=0.15)
    dep_idx = departure_hour_index(forecast_times, departure_utc)
    offset = max(1, min(2, int(peak_offset_h)))
    peak = min(max(0, dep_idx + offset), max(0, len(forecast_times) - 1) if forecast_times else dep_idx + offset)

    return StormConfig(
        lat=lat,
        lng=lng,
        radius_deg=radius_deg,
        peak_hour=peak,
        peak_offset_h=offset,
    )


def apply_storm_arrays(
    *,
    lat: float,
    lng: float,
    wind_mph: Sequence[float],
    precip_in: Sequence[float],
    snow_in: Sequence[float],
    storm: StormConfig,
) -> tuple[list[float], list[float], list[float]]:
    """
    Wind + rain boosts only; snow returned unchanged; no minimum floors.

    Influence is linear in distance out to radius_deg; temporal weight is a
    narrow Gaussian around peak_hour.
    """
    wind = list(wind_mph)
    precip = list(precip_in)
    snow = list(snow_in)

    dist = math.hypot(lat - storm.lat, lng - storm.lng)
    influence = max(0.0, 1.0 - dist / max(1e-6, storm.radius_deg))
    if influence <= 0.0:
        return wind, precip, snow

    for i in range(len(wind)):
        hour_w = math.exp(-0.5 * ((i - storm.peak_hour) / 2.0) ** 2)
        factor = influence * hour_w
        wind[i] = wind[i] + storm.wind_boost_mph * factor
        precip[i] = precip[i] + storm.rain_boost_in * factor

    return wind, precip, snow
