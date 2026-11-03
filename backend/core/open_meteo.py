"""
Open-Meteo request params + response parsing (Django-free).

Open-Meteo defaults are km/h, mm, and cm. We always request:
  - wind_speed_unit=mph
  - precipitation_unit=inch
and convert snowfall from cm → inches explicitly (API has no inch option for snow).

Multi-location: pass comma-separated latitude/longitude lists in one GET.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.units import cm_to_inches

# Explicit unit overrides — never rely on Open-Meteo defaults (km/h, mm).
WIND_SPEED_UNIT = "mph"
PRECIPITATION_UNIT = "inch"
# 48 hourly slots ⇒ 2 forecast days
HOURLY_HORIZON = 48


@dataclass(frozen=True)
class ParsedHourly:
    times: list[str]
    wind_mph: list[float]
    precip_in: list[float]
    snow_in: list[float]


def _forecast_days_for_hours(hours: int) -> int:
    return max(1, (max(1, hours) + 23) // 24)


def forecast_query_params(
    lat: float,
    lng: float,
    *,
    forecast_days: int | None = None,
    forecast_hours: int = HOURLY_HORIZON,
) -> dict[str, str | int | float]:
    """Query params for a single-coordinate GET /v1/forecast."""
    days = forecast_days if forecast_days is not None else _forecast_days_for_hours(forecast_hours)
    return {
        "latitude": lat,
        "longitude": lng,
        "hourly": "wind_speed_10m,precipitation,snowfall",
        "wind_speed_unit": WIND_SPEED_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
        "forecast_days": days,
        "timezone": "UTC",
    }


def forecast_query_params_multi(
    latitudes: Sequence[float],
    longitudes: Sequence[float],
    *,
    forecast_hours: int = HOURLY_HORIZON,
) -> dict[str, str | int]:
    """
    One request for many points: latitude=lat1,lat2,… & longitude=lng1,lng2,…
    Open-Meteo returns a JSON array (one object per location).
    """
    if len(latitudes) != len(longitudes):
        raise ValueError("latitudes and longitudes length mismatch")
    if not latitudes:
        raise ValueError("need at least one coordinate")
    days = _forecast_days_for_hours(forecast_hours)
    return {
        "latitude": ",".join(f"{lat:.5f}" for lat in latitudes),
        "longitude": ",".join(f"{lng:.5f}" for lng in longitudes),
        "hourly": "wind_speed_10m,precipitation,snowfall",
        "wind_speed_unit": WIND_SPEED_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
        "forecast_days": days,
        "timezone": "UTC",
    }


def parse_hourly_payload(hourly: dict, *, max_hours: int = HOURLY_HORIZON) -> ParsedHourly:
    """
    Parse Open-Meteo `hourly` object into mph / inches / inches.

    Wind and precip must already be requested in mph / inch.
    Snowfall is always returned in cm → convert with cm_to_inches.
    Truncates to `max_hours` (default 48).
    """
    times = list(hourly.get("time") or [])[:max_hours]
    n = len(times)
    wind_mph = [float(v or 0) for v in (hourly.get("wind_speed_10m") or [])][:n]
    precip_in = [float(v or 0) for v in (hourly.get("precipitation") or [])][:n]
    snow_cm = [float(v or 0) for v in (hourly.get("snowfall") or [])][:n]
    snow_in = [cm_to_inches(v) for v in snow_cm][:n]

    while len(wind_mph) < n:
        wind_mph.append(0.0)
    while len(precip_in) < n:
        precip_in.append(0.0)
    while len(snow_in) < n:
        snow_in.append(0.0)

    return ParsedHourly(
        times=times,
        wind_mph=wind_mph,
        precip_in=precip_in,
        snow_in=snow_in,
    )
