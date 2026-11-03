"""Every threshold boundary in the wind / rain / snow risk tables."""

import pytest

from core.risk import (
    RiskLevel,
    WeatherSample,
    classify_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
    worst_of,
)


# --- Wind: Low <25 | Mod 25–34 | High 35–44 | Severe 45–54 | No Travel ≥55 ---

@pytest.mark.parametrize(
    "wind, expected",
    [
        (0.0, RiskLevel.LOW),
        (24.999, RiskLevel.LOW),
        (25.0, RiskLevel.MODERATE),
        (34.0, RiskLevel.MODERATE),
        (34.999, RiskLevel.MODERATE),
        (35.0, RiskLevel.HIGH),
        (44.0, RiskLevel.HIGH),
        (44.999, RiskLevel.HIGH),
        (45.0, RiskLevel.SEVERE),
        (54.0, RiskLevel.SEVERE),
        (54.999, RiskLevel.SEVERE),
        (55.0, RiskLevel.NO_TRAVEL),
        (80.0, RiskLevel.NO_TRAVEL),
    ],
)
def test_wind_boundaries(wind, expected):
    assert classify_wind(wind) == expected


# --- Rain: Low <0.10 | Mod 0.10–0.25 | High 0.25–0.50 | Sev 0.50–1.00 | NT >1.00 ---

@pytest.mark.parametrize(
    "rain, expected",
    [
        (0.0, RiskLevel.LOW),
        (0.0999, RiskLevel.LOW),
        (0.10, RiskLevel.MODERATE),
        (0.2499, RiskLevel.MODERATE),
        (0.25, RiskLevel.HIGH),  # shared edge → higher band
        (0.4999, RiskLevel.HIGH),
        (0.50, RiskLevel.SEVERE),  # shared edge → higher band
        (1.00, RiskLevel.SEVERE),
        (1.0001, RiskLevel.NO_TRAVEL),
        (2.0, RiskLevel.NO_TRAVEL),
    ],
)
def test_rain_boundaries(rain, expected):
    assert classify_rain(rain) == expected


# --- Snow: Low <0.5 | Mod 0.5–1.0 | High 1.0–2.0 | Sev 2.0–3.0 | NT >3.0 ---

@pytest.mark.parametrize(
    "snow, expected",
    [
        (0.0, RiskLevel.LOW),
        (0.4999, RiskLevel.LOW),
        (0.5, RiskLevel.MODERATE),
        (0.999, RiskLevel.MODERATE),
        (1.0, RiskLevel.HIGH),  # shared edge → higher band
        (1.999, RiskLevel.HIGH),
        (2.0, RiskLevel.SEVERE),  # shared edge → higher band
        (3.0, RiskLevel.SEVERE),
        (3.0001, RiskLevel.NO_TRAVEL),
        (5.0, RiskLevel.NO_TRAVEL),
    ],
)
def test_snow_boundaries(snow, expected):
    assert classify_snow(snow) == expected


def test_worst_of_picks_maximum():
    assert worst_of([RiskLevel.LOW, RiskLevel.SEVERE, RiskLevel.HIGH]) == RiskLevel.SEVERE
    assert worst_of([]) == RiskLevel.LOW


def test_classify_checkpoint_uses_worst_condition():
    # High rain, low wind/snow → High (no load upgrade)
    weather = WeatherSample(wind_mph=10, precip_in_hr=0.3, snow_in_hr=0.0)
    assert classify_checkpoint(weather, load_lb=10_000) == RiskLevel.HIGH
