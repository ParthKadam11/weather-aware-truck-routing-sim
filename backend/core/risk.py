"""
Weather risk classification and load-weight upgrades.

Risk levels (ordered worst → best for scoring):
  No Travel > Severe > High > Moderate > Low

Per-condition tables (from the assessment PDF). At overlapping numeric
boundaries we take the *higher* severity so scoring is conservative.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class RiskLevel(IntEnum):
    """Integer values double as average-risk scores (Low=1 … No Travel=5)."""

    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4
    NO_TRAVEL = 5


RISK_LABELS = {
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}


@dataclass(frozen=True)
class WeatherSample:
    """Weather at a single point / hour, already in assessment units."""

    wind_mph: float
    precip_in_hr: float
    snow_in_hr: float


def classify_wind(wind_mph: float) -> RiskLevel:
    """
    Wind (mph):
      Low <25 | Moderate 25–34 | High 35–44 | Severe 45–54 | No Travel ≥55
    """
    if wind_mph >= 55:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= 45:
        return RiskLevel.SEVERE
    if wind_mph >= 35:
        return RiskLevel.HIGH
    if wind_mph >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(precip_in_hr: float) -> RiskLevel:
    """
    Rain (in/hr):
      Low <0.10 | Moderate 0.10–0.25 | High 0.25–0.50
      Severe 0.50–1.00 | No Travel >1.00

    Shared edges (0.25, 0.50) resolve to the higher band.
    """
    if precip_in_hr > 1.00:
        return RiskLevel.NO_TRAVEL
    if precip_in_hr >= 0.50:
        return RiskLevel.SEVERE
    if precip_in_hr >= 0.25:
        return RiskLevel.HIGH
    if precip_in_hr >= 0.10:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(snow_in_hr: float) -> RiskLevel:
    """
    Snow (in/hr):
      Low <0.5 | Moderate 0.5–1.0 | High 1.0–2.0
      Severe 2.0–3.0 | No Travel >3.0

    Shared edges (1.0, 2.0) resolve to the higher band.
    """
    if snow_in_hr > 3.0:
        return RiskLevel.NO_TRAVEL
    if snow_in_hr >= 2.0:
        return RiskLevel.SEVERE
    if snow_in_hr >= 1.0:
        return RiskLevel.HIGH
    if snow_in_hr >= 0.5:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def worst_of(levels: Iterable[RiskLevel]) -> RiskLevel:
    return max(levels, default=RiskLevel.LOW)


def apply_load_rules(wind_mph: float, load_lb: float, base: RiskLevel) -> RiskLevel:
    """
    Load upgrades (assessment PDF):
      • ≥55 mph → No Travel for any load
      • 45–54 mph + >30,000 lb → No Travel
      • 35–44 mph + >40,000 lb → Severe
    Never downgrades an already-worse base level.
    """
    upgraded = base

    if wind_mph >= 55:
        upgraded = RiskLevel.NO_TRAVEL
    elif 45 <= wind_mph < 55 and load_lb > 30_000:
        upgraded = max(upgraded, RiskLevel.NO_TRAVEL)
    elif 35 <= wind_mph < 45 and load_lb > 40_000:
        upgraded = max(upgraded, RiskLevel.SEVERE)

    return upgraded


def classify_checkpoint(weather: WeatherSample, load_lb: float) -> RiskLevel:
    """Worst of wind/rain/snow, then apply load rules based on wind + weight."""
    base = worst_of(
        [
            classify_wind(weather.wind_mph),
            classify_rain(weather.precip_in_hr),
            classify_snow(weather.snow_in_hr),
        ]
    )
    return apply_load_rules(weather.wind_mph, load_lb, base)


def label(level: RiskLevel) -> str:
    return RISK_LABELS[level]
