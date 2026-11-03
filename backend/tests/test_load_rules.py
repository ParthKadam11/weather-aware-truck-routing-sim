"""Every load-weight upgrade rule from the assessment PDF."""

import pytest

from core.risk import RiskLevel, WeatherSample, apply_load_rules, classify_checkpoint, classify_wind


# --- ≥55 mph → No Travel for any load ---

@pytest.mark.parametrize("load", [0, 1, 30_000, 30_001, 40_000, 40_001, 80_000])
@pytest.mark.parametrize("wind", [55.0, 55.001, 80.0])
def test_wind_ge_55_any_load_is_no_travel(wind, load):
    base = classify_wind(wind)
    assert apply_load_rules(wind, load, base) == RiskLevel.NO_TRAVEL
    weather = WeatherSample(wind_mph=wind, precip_in_hr=0.0, snow_in_hr=0.0)
    assert classify_checkpoint(weather, load) == RiskLevel.NO_TRAVEL


# --- 45–54 mph + >30,000 lb → No Travel ---

@pytest.mark.parametrize("wind", [45.0, 50.0, 54.0, 54.999])
def test_wind_45_54_over_30k_no_travel(wind):
    base = classify_wind(wind)
    assert base == RiskLevel.SEVERE
    assert apply_load_rules(wind, 30_001, base) == RiskLevel.NO_TRAVEL


@pytest.mark.parametrize("wind", [45.0, 50.0, 54.0])
def test_wind_45_54_at_30k_stays_severe(wind):
    base = classify_wind(wind)
    assert apply_load_rules(wind, 30_000, base) == RiskLevel.SEVERE


def test_wind_just_below_45_does_not_use_30k_rule():
    # 44.999 is High by wind; 30,001 lb is NOT enough for the 35–44/>40k rule
    wind = 44.999
    base = classify_wind(wind)
    assert base == RiskLevel.HIGH
    assert apply_load_rules(wind, 30_001, base) == RiskLevel.HIGH


# --- 35–44 mph + >40,000 lb → Severe ---

@pytest.mark.parametrize("wind", [35.0, 40.0, 44.0, 44.999])
def test_wind_35_44_over_40k_severe(wind):
    base = classify_wind(wind)
    assert base == RiskLevel.HIGH
    assert apply_load_rules(wind, 40_001, base) == RiskLevel.SEVERE


@pytest.mark.parametrize("wind", [35.0, 40.0, 44.0])
def test_wind_35_44_at_40k_stays_high(wind):
    base = classify_wind(wind)
    assert apply_load_rules(wind, 40_000, base) == RiskLevel.HIGH


def test_wind_just_below_35_no_load_upgrade():
    wind = 34.999
    base = classify_wind(wind)
    assert base == RiskLevel.MODERATE
    assert apply_load_rules(wind, 100_000, base) == RiskLevel.MODERATE


def test_load_rule_never_downgrades():
    assert apply_load_rules(10.0, 1_000, RiskLevel.NO_TRAVEL) == RiskLevel.NO_TRAVEL


def test_end_to_end_checkpoint_load_upgrade():
    # Wind 40 → High; rain 0.15 → Moderate; worst = High.
    # >40k lb upgrades High → Severe; at exactly 40k stays High.
    weather = WeatherSample(wind_mph=40.0, precip_in_hr=0.15, snow_in_hr=0.0)
    assert classify_checkpoint(weather, load_lb=50_000) == RiskLevel.SEVERE
    assert classify_checkpoint(weather, load_lb=40_000) == RiskLevel.HIGH
