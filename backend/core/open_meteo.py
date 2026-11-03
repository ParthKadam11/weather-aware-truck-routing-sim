"""
Open-Meteo request params + response parsing (Django-free).

Open-Meteo defaults are km/h, mm, and cm. We always request:
  - wind_speed_unit=mph
  - precipitation_unit=inch
and convert snowfall from cm → inches explicitly (API has no inch option for snow).

Multi-location: pass comma-separated latitude/longitude lists in one GET.
forecast_hours=48 starts at the current UTC hour so index 0 = "now".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.units import cm_to_inches

# Explicit unit overrides — never rely on Open-Meteo defaults (km/h, mm).
WIND_SPEED_UNIT = "mph"
PRECIPITATION_UNIT = "inch"
# 48 hourly slots starting at the current UTC hour
HOURLY_HORIZON = 48


@dataclass(frozen=True)
class ParsedHourly:
    times: list[str]
    wind_mph: list[float]
    precip_in: list[float]
    snow_in: list[float]


def forecast_query_params(
    lat: float,
    lng: float,
    *,
    forecast_days: int | None = None,
    forecast_hours: int = HOURLY_HORIZON,
) -> dict[str, str | int | float]:
    """
    Query params for a single-coordinate GET /v1/forecast.

    Uses forecast_hours (not forecast_days) so the series begins at the
    current UTC hour — slider index 0 = now.
    """
    del forecast_days  # horizon is hour-based; days would shift the start window
    return {
        "latitude": lat,
        "longitude": lng,
        "hourly": "wind_speed_10m,precipitation,snowfall",
        "wind_speed_unit": WIND_SPEED_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
        "forecast_hours": int(forecast_hours),
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

    forecast_hours=48 → hourly axis starts at the current UTC hour.
    """
    if len(latitudes) != len(longitudes):
        raise ValueError("latitudes and longitudes length mismatch")
    if not latitudes:
        raise ValueError("need at least one coordinate")
    return {
        "latitude": ",".join(f"{lat:.5f}" for lat in latitudes),
        "longitude": ",".join(f"{lng:.5f}" for lng in longitudes),
        "hourly": "wind_speed_10m,precipitation,snowfall",
        "wind_speed_unit": WIND_SPEED_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
        "forecast_hours": int(forecast_hours),
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
