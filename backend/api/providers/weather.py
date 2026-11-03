"""
Open-Meteo hourly weather + optional demo-storm overlay.

Open-Meteo is free / no key. We request:
  - wind_speed_10m in mph
  - precipitation in inch
  - snowfall in cm (converted to inches via core.units)
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import httpx
from django.conf import settings

from core.cache import weather_cache
from core.risk import WeatherSample
from core.units import cm_to_inches


@dataclass(frozen=True)
class HourlySeries:
    """Hourly arrays aligned by index; times are UTC ISO strings from the API."""

    times: list[str]  # e.g. "2026-06-01T14:00"
    wind_mph: list[float]
    precip_in: list[float]
    snow_in: list[float]
    lat: float
    lng: float


class WeatherError(Exception):
    pass


def _cache_key(lat: float, lng: float, start: str, end: str) -> str:
    raw = f"{lat:.3f},{lng:.3f},{start},{end}"
    return "wx:" + hashlib.sha1(raw.encode()).hexdigest()


def _parse_series(lat: float, lng: float, hourly: dict) -> HourlySeries:
    times = hourly.get("time") or []
    wind = [float(v or 0) for v in (hourly.get("wind_speed_10m") or [])]
    precip = [float(v or 0) for v in (hourly.get("precipitation") or [])]
    snow_cm = [float(v or 0) for v in (hourly.get("snowfall") or [])]
    snow_in = [cm_to_inches(v) for v in snow_cm]
    n = len(times)
    return HourlySeries(
        times=times,
        wind_mph=wind[:n],
        precip_in=precip[:n],
        snow_in=snow_in[:n],
        lat=lat,
        lng=lng,
    )


def fetch_hourly(
    lat: float,
    lng: float,
    *,
    forecast_days: int = 3,
    client: httpx.Client | None = None,
) -> HourlySeries:
    """Fetch (or cache) hourly forecast for one coordinate."""
    key = _cache_key(lat, lng, "now", str(forecast_days))
    cached = weather_cache.get(key)
    if cached is not None:
        return cached

    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        url = f"{settings.OPEN_METEO_BASE_URL.rstrip('/')}/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "hourly": "wind_speed_10m,precipitation,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        series = _parse_series(lat, lng, data.get("hourly") or {})
        weather_cache.set(key, series, ttl_s=settings.WEATHER_CACHE_TTL_S)
        return series
    except httpx.HTTPError as exc:
        raise WeatherError(f"weather fetch failed: {exc}") from exc
    finally:
        if owns:
            client.close()


def fetch_hourly_batch(
    points: Sequence[tuple[float, float]],
    *,
    forecast_days: int = 3,
    client: httpx.Client | None = None,
) -> list[HourlySeries]:
    """
    Batch by unique rounded coordinates to cut API calls.
    Open-Meteo also supports multi-lat/lng in one request; we group uniques.
    """
    owns = client is None
    client = client or httpx.Client(timeout=45.0)
    try:
        # Deduplicate at ~100m precision
        unique: dict[tuple[float, float], list[int]] = {}
        for i, (lat, lng) in enumerate(points):
            key = (round(lat, 3), round(lng, 3))
            unique.setdefault(key, []).append(i)

        results: list[HourlySeries | None] = [None] * len(points)
        for (lat, lng), indices in unique.items():
            series = fetch_hourly(lat, lng, forecast_days=forecast_days, client=client)
            for i in indices:
                results[i] = series

        assert all(r is not None for r in results)
        return results  # type: ignore[return-value]
    finally:
        if owns:
            client.close()


def sample_at_eta(series: HourlySeries, eta_utc: datetime) -> WeatherSample:
    """Pick the hourly slot closest to (floor of) the ETA hour."""
    if eta_utc.tzinfo is None:
        eta_utc = eta_utc.replace(tzinfo=timezone.utc)
    else:
        eta_utc = eta_utc.astimezone(timezone.utc)

    if not series.times:
        return WeatherSample(0.0, 0.0, 0.0)

    # Times look like "2026-06-01T14:00"
    target = eta_utc.replace(minute=0, second=0, microsecond=0)
    target_str = target.strftime("%Y-%m-%dT%H:%M")

    if target_str in series.times:
        idx = series.times.index(target_str)
    else:
        # Fall back to nearest index by parsing
        idx = 0
        best = abs(
            (
                datetime.fromisoformat(series.times[0]).replace(tzinfo=timezone.utc) - target
            ).total_seconds()
        )
        for i, t in enumerate(series.times):
            dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            d = abs((dt - target).total_seconds())
            if d < best:
                best = d
                idx = i

    idx = min(idx, len(series.wind_mph) - 1)
    return WeatherSample(
        wind_mph=series.wind_mph[idx],
        precip_in_hr=series.precip_in[idx],
        snow_in_hr=series.snow_in[idx],
    )


def apply_demo_storm(
    series: HourlySeries,
    *,
    storm_lat: float,
    storm_lng: float,
    peak_hour: int = 6,
) -> HourlySeries:
    """
    Overlay a fake intense storm near (storm_lat, storm_lng) peaking at hour index.

    Used when DEMO_STORM=1 so reviewers see recommendation changes without
    waiting for real severe weather. Keeps a baseline boost near the center
    even off-peak so trips that don't hit `peak_hour` still show elevated risk.
    """
    wind = list(series.wind_mph)
    precip = list(series.precip_in)
    snow = list(series.snow_in)

    # Distance from storm center (degrees ≈ rough)
    dist = math.hypot(series.lat - storm_lat, series.lng - storm_lng)
    # Influence radius ~2.0 degrees — wide enough to clip some but not all alts
    influence = max(0.0, 1.0 - dist / 2.0)

    for i in range(len(wind)):
        # Gaussian peak + 0.35 floor so off-peak hours still look stormy nearby
        hour_w = 0.35 + 0.65 * math.exp(-0.5 * ((i - peak_hour) / 6.0) ** 2)
        factor = influence * hour_w
        wind[i] = max(wind[i], 18.0 + 50.0 * factor)  # up to ~68 mph at center
        precip[i] = max(precip[i], 0.05 + 1.2 * factor)
        snow[i] = max(snow[i], 0.2 + 3.5 * factor)

    return HourlySeries(
        times=list(series.times),
        wind_mph=wind,
        precip_in=precip,
        snow_in=snow,
        lat=series.lat,
        lng=series.lng,
    )


def peak_hour_for_departure(series: HourlySeries, departure_utc: datetime) -> int:
    """Align demo-storm peak with the trip's departure hour in the forecast axis."""
    if not series.times:
        return 8
    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=timezone.utc)
    target = departure_utc.astimezone(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    target_str = target.strftime("%Y-%m-%dT%H:%M")
    if target_str in series.times:
        return series.times.index(target_str)
    # Nearest
    best_i, best_d = 0, float("inf")
    for i, t in enumerate(series.times):
        dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        d = abs((dt - target).total_seconds())
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def maybe_demo(series: HourlySeries, corridor_mid: tuple[float, float]) -> HourlySeries:
    if not settings.DEMO_STORM:
        return series
    # Place storm slightly offset from corridor midpoint so some routes miss it
    lat, lng = corridor_mid
    return apply_demo_storm(series, storm_lat=lat + 0.4, storm_lng=lng - 0.3, peak_hour=8)
