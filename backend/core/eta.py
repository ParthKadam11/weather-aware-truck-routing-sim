"""ETA calculation at checkpoints from departure time + cumulative travel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from core.checkpoints import Checkpoint


@dataclass(frozen=True)
class CheckpointEta:
    checkpoint_index: int
    eta_utc: datetime
    duration_from_start_s: float


def etas_along_route(
    checkpoints: Sequence[Checkpoint],
    departure_utc: datetime,
    total_duration_s: float,
    total_distance_m: float,
) -> list[CheckpointEta]:
    """
    Estimate ETA at each checkpoint by proportion of distance traveled.

    Assumes roughly constant average speed over the whole route (OSRM does not
    give per-segment durations on the free public demo without extra steps).
    `departure_utc` must be timezone-aware; naive datetimes are treated as UTC.
    """
    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=timezone.utc)
    else:
        departure_utc = departure_utc.astimezone(timezone.utc)

    if total_distance_m <= 0:
        raise ValueError("total_distance_m must be positive")
    if total_duration_s < 0:
        raise ValueError("total_duration_s must be non-negative")

    results: list[CheckpointEta] = []
    for cp in checkpoints:
        frac = min(1.0, max(0.0, cp.distance_m / total_distance_m))
        duration_s = total_duration_s * frac
        results.append(
            CheckpointEta(
                checkpoint_index=cp.index,
                eta_utc=departure_utc + timedelta(seconds=duration_s),
                duration_from_start_s=duration_s,
            )
        )
    return results


def to_local(dt_utc: datetime, tz_name: str) -> datetime:
    """Convert a UTC datetime to a named IANA timezone for display."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(tz_name))


def forecast_hour_index(eta_utc: datetime, forecast_start_utc: datetime) -> int:
    """
    Which hourly forecast slot matches this ETA?

    Returns floor hours since forecast_start (clamped ≥ 0).
    """
    if eta_utc.tzinfo is None:
        eta_utc = eta_utc.replace(tzinfo=timezone.utc)
    if forecast_start_utc.tzinfo is None:
        forecast_start_utc = forecast_start_utc.replace(tzinfo=timezone.utc)

    delta = eta_utc - forecast_start_utc.astimezone(timezone.utc)
    hours = int(delta.total_seconds() // 3600)
    return max(0, hours)
