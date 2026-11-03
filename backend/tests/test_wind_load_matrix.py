"""
Wind boundary × load matrix.

Winds: 24.9, 25, 34.9, 35, 44.9, 45, 54.9, 55
Loads: 30000, 30001, 40000, 40001

Rain/snow held at zero so only wind + load rules apply.
"""

import pytest

from core.risk import RiskLevel, WeatherSample, classify_checkpoint


WINDS = [24.9, 25.0, 34.9, 35.0, 44.9, 45.0, 54.9, 55.0]
LOADS = [30_000, 30_001, 40_000, 40_001]


def _expected(wind: float, load: float) -> RiskLevel:
    """Mirror risk.py tables + load rules for the matrix."""
    if wind >= 55:
        base = RiskLevel.NO_TRAVEL
    elif wind >= 45:
        base = RiskLevel.SEVERE
    elif wind >= 35:
        base = RiskLevel.HIGH
    elif wind >= 25:
        base = RiskLevel.MODERATE
    else:
        base = RiskLevel.LOW

    if wind >= 55:
        return RiskLevel.NO_TRAVEL
    if 45 <= wind < 55 and load > 30_000:
        return RiskLevel.NO_TRAVEL
    if 35 <= wind < 45 and load > 40_000:
        return max(base, RiskLevel.SEVERE)
    return base


@pytest.mark.parametrize("wind", WINDS)
@pytest.mark.parametrize("load", LOADS)
def test_wind_load_matrix(wind, load):
    weather = WeatherSample(wind_mph=wind, precip_in_hr=0.0, snow_in_hr=0.0)
    assert classify_checkpoint(weather, load) == _expected(wind, load)


# Explicit named cases for the exact values requested
@pytest.mark.parametrize(
    "wind, load, expected",
    [
        # Below moderate
        (24.9, 30_000, RiskLevel.LOW),
        (24.9, 30_001, RiskLevel.LOW),
        (24.9, 40_000, RiskLevel.LOW),
        (24.9, 40_001, RiskLevel.LOW),
        # Moderate band — no load upgrade
        (25.0, 30_000, RiskLevel.MODERATE),
        (25.0, 40_001, RiskLevel.MODERATE),
        (34.9, 30_000, RiskLevel.MODERATE),
        (34.9, 40_001, RiskLevel.MODERATE),
        # High band — upgrade only when >40k
        (35.0, 30_000, RiskLevel.HIGH),
        (35.0, 30_001, RiskLevel.HIGH),
        (35.0, 40_000, RiskLevel.HIGH),
        (35.0, 40_001, RiskLevel.SEVERE),
        (44.9, 40_000, RiskLevel.HIGH),
        (44.9, 40_001, RiskLevel.SEVERE),
        # Severe band — upgrade to No Travel when >30k
        (45.0, 30_000, RiskLevel.SEVERE),
        (45.0, 30_001, RiskLevel.NO_TRAVEL),
        (45.0, 40_000, RiskLevel.NO_TRAVEL),
        (45.0, 40_001, RiskLevel.NO_TRAVEL),
        (54.9, 30_000, RiskLevel.SEVERE),
        (54.9, 30_001, RiskLevel.NO_TRAVEL),
        (54.9, 40_000, RiskLevel.NO_TRAVEL),
        (54.9, 40_001, RiskLevel.NO_TRAVEL),
        # No Travel wind — any load
        (55.0, 30_000, RiskLevel.NO_TRAVEL),
        (55.0, 30_001, RiskLevel.NO_TRAVEL),
        (55.0, 40_000, RiskLevel.NO_TRAVEL),
        (55.0, 40_001, RiskLevel.NO_TRAVEL),
    ],
)
def test_explicit_wind_load_boundaries(wind, load, expected):
    weather = WeatherSample(wind_mph=wind, precip_in_hr=0.0, snow_in_hr=0.0)
    assert classify_checkpoint(weather, load) == expected
