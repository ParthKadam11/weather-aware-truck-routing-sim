"""
Open-Meteo hourly weather + optional demo-storm overlay.

Fetches ALL checkpoint coordinates in ONE multi-location request
(comma-separated lat/lng lists, 48 hourly values). Samples are cached per
rounded lat/lng + forecast hour.
"""

from __future__ import annotations

import hashlib
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import httpx
from django.conf import settings

from core.cache import weather_cache
from core.open_meteo import (
    HOURLY_HORIZON,
    forecast_query_params,
    forecast_query_params_multi,
    parse_hourly_payload,
)
from core.risk import WeatherSample


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


def _round_ll(lat: float, lng: float) -> tuple[float, float]:
    return (round(lat, 3), round(lng, 3))


def _series_cache_key(lat: float, lng: float) -> str:
    rlat, rlng = _round_ll(lat, lng)
    raw = f"series:{rlat},{rlng}:h{HOURLY_HORIZON}"
    return "wx:" + hashlib.sha1(raw.encode()).hexdigest()


def _hour_cache_key(lat: float, lng: float, hour_key: str) -> str:
    """Cache key for a single ETA hour sample: rounded lat/lng + hour."""
    rlat, rlng = _round_ll(lat, lng)
    raw = f"hour:{rlat},{rlng}:{hour_key}"
    return "wxh:" + hashlib.sha1(raw.encode()).hexdigest()


def _eta_hour_key(eta_utc: datetime) -> str:
    if eta_utc.tzinfo is None:
        eta_utc = eta_utc.replace(tzinfo=timezone.utc)
    else:
        eta_utc = eta_utc.astimezone(timezone.utc)
    return eta_utc.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def _parse_series(lat: float, lng: float, hourly: dict) -> HourlySeries:
    parsed = parse_hourly_payload(hourly, max_hours=HOURLY_HORIZON)
    return HourlySeries(
        times=parsed.times,
        wind_mph=parsed.wind_mph,
        precip_in=parsed.precip_in,
        snow_in=parsed.snow_in,
        lat=lat,
        lng=lng,
    )


def _normalize_multi_response(data: object) -> list[dict]:
    """Open-Meteo returns a list for multi-location, object for single."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise WeatherError(f"unexpected Open-Meteo payload type: {type(data)}")


def fetch_hourly(
    lat: float,
    lng: float,
    *,
    forecast_days: int | None = None,
    client: httpx.Client | None = None,
) -> HourlySeries:
    """Fetch (or cache) 48h hourly forecast for one coordinate."""
    key = _series_cache_key(lat, lng)
    cached = weather_cache.get(key)
    if cached is not None:
        return cached

    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        url = f"{settings.OPEN_METEO_BASE_URL.rstrip('/')}/v1/forecast"
        params = forecast_query_params(
            lat, lng, forecast_days=forecast_days, forecast_hours=HOURLY_HORIZON
        )
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        # multi-endpoint may wrap even one point as a list
        loc = _normalize_multi_response(data)[0]
        series = _parse_series(lat, lng, loc.get("hourly") or {})
        weather_cache.set(key, series, ttl_s=settings.WEATHER_CACHE_TTL_S)
        return series
    except httpx.HTTPError as exc:
        raise WeatherError(f"weather fetch failed: {exc}") from exc
    finally:
        if owns:
            client.close()


# Open-Meteo multi-location URL length / practicality cap per request
BATCH_CHUNK_SIZE = 100


def _fetch_chunk(
    missing: list[tuple[float, float]],
    *,
    forecast_hours: int,
    forecast_days: int | None,
) -> list[tuple[tuple[float, float], HourlySeries]]:
    """Fetch one ≤BATCH_CHUNK_SIZE chunk; uses its own httpx client (thread-safe)."""
    url = f"{settings.OPEN_METEO_BASE_URL.rstrip('/')}/v1/forecast"
    lats = [m[0] for m in missing]
    lngs = [m[1] for m in missing]
    params = forecast_query_params_multi(lats, lngs, forecast_hours=forecast_hours)
    if forecast_days is not None:
        params["forecast_days"] = max(int(params["forecast_days"]), int(forecast_days))
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        locations = _normalize_multi_response(resp.json())
    if len(locations) != len(missing):
        raise WeatherError(
            f"Open-Meteo returned {len(locations)} locations, expected {len(missing)}"
        )
    out: list[tuple[tuple[float, float], HourlySeries]] = []
    for (lat, lng), loc in zip(missing, locations):
        series = _parse_series(lat, lng, loc.get("hourly") or {})
        weather_cache.set(
            _series_cache_key(lat, lng), series, ttl_s=settings.WEATHER_CACHE_TTL_S
        )
        out.append(((lat, lng), series))
    return out


def fetch_hourly_batch(
    points: Sequence[tuple[float, float]],
    *,
    forecast_days: int | None = None,
    forecast_hours: int = HOURLY_HORIZON,
    client: httpx.Client | None = None,
) -> list[HourlySeries]:
    """
    Fetch 48h hourly forecasts for many coordinates.

    Dedupes by rounded lat/lng, serves from cache when possible, and for misses
    chunks at ~100 points with parallel Open-Meteo requests (ThreadPoolExecutor).
    """
    del client  # workers own their clients
    if not points:
        return []

    unique_order: list[tuple[float, float]] = []
    index_map: dict[tuple[float, float], list[int]] = {}
    for i, (lat, lng) in enumerate(points):
        key = _round_ll(lat, lng)
        if key not in index_map:
            index_map[key] = []
            unique_order.append(key)
        index_map[key].append(i)

    results: list[HourlySeries | None] = [None] * len(points)
    missing: list[tuple[float, float]] = []
    for key in unique_order:
        cached = weather_cache.get(_series_cache_key(key[0], key[1]))
        if cached is not None:
            for i in index_map[key]:
                results[i] = cached
        else:
            missing.append(key)

    if missing:
        chunks = [
            missing[i : i + BATCH_CHUNK_SIZE]
            for i in range(0, len(missing), BATCH_CHUNK_SIZE)
        ]
        try:
            workers = min(8, len(chunks))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(
                        _fetch_chunk,
                        chunk,
                        forecast_hours=forecast_hours,
                        forecast_days=forecast_days,
                    )
                    for chunk in chunks
                ]
                for fut in as_completed(futures):
                    for (lat, lng), series in fut.result():
                        for i in index_map[(lat, lng)]:
                            results[i] = series
        except httpx.HTTPError as exc:
            raise WeatherError(f"weather batch fetch failed: {exc}") from exc

    assert all(r is not None for r in results)
    return results  # type: ignore[return-value]


def sample_at_eta(series: HourlySeries, eta_utc: datetime) -> WeatherSample:
    """
    Pick the hourly slot for this ETA.

    Caches the sample under rounded lat/lng + hour so repeat lookups are free.
    """
    hour_key = _eta_hour_key(eta_utc)
    cache_key = _hour_cache_key(series.lat, series.lng, hour_key)
    cached = weather_cache.get(cache_key)
    if cached is not None:
        return cached

    if not series.times:
        sample = WeatherSample(0.0, 0.0, 0.0)
        weather_cache.set(cache_key, sample, ttl_s=settings.WEATHER_CACHE_TTL_S)
        return sample

    if hour_key in series.times:
        idx = series.times.index(hour_key)
    else:
        target = datetime.fromisoformat(hour_key).replace(tzinfo=timezone.utc)
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
    sample = WeatherSample(
        wind_mph=series.wind_mph[idx],
        precip_in_hr=series.precip_in[idx],
        snow_in_hr=series.snow_in[idx],
    )
    weather_cache.set(cache_key, sample, ttl_s=settings.WEATHER_CACHE_TTL_S)
    return sample


def apply_demo_storm(
    series: HourlySeries,
    *,
    storm_lat: float,
    storm_lng: float,
    peak_hour: int = 6,
) -> HourlySeries:
    """
    Overlay a fake intense storm near (storm_lat, storm_lng) peaking at hour index.
    """
    wind = list(series.wind_mph)
    precip = list(series.precip_in)
    snow = list(series.snow_in)

    dist = math.hypot(series.lat - storm_lat, series.lng - storm_lng)
    influence = max(0.0, 1.0 - dist / 2.0)

    for i in range(len(wind)):
        hour_w = 0.35 + 0.65 * math.exp(-0.5 * ((i - peak_hour) / 6.0) ** 2)
        factor = influence * hour_w
        wind[i] = max(wind[i], 18.0 + 50.0 * factor)
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
    lat, lng = corridor_mid
    return apply_demo_storm(series, storm_lat=lat + 0.4, storm_lng=lng - 0.3, peak_hour=8)
