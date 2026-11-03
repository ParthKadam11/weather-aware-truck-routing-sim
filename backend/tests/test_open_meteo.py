"""Open-Meteo unit params, multi-location lists, snowfall cm → inches."""

from core.open_meteo import (
    HOURLY_HORIZON,
    PRECIPITATION_UNIT,
    WIND_SPEED_UNIT,
    forecast_query_params,
    forecast_query_params_multi,
    parse_hourly_payload,
)
from core.units import cm_to_inches


def test_forecast_params_override_default_units():
    params = forecast_query_params(19.07, 72.87, forecast_hours=HOURLY_HORIZON)
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["wind_speed_unit"] == WIND_SPEED_UNIT
    assert params["precipitation_unit"] == PRECIPITATION_UNIT
    assert params["forecast_hours"] == 48
    assert "forecast_days" not in params
    assert params["timezone"] == "UTC"
    assert params["wind_speed_unit"] != "kmh"
    assert params["precipitation_unit"] != "mm"
    assert "wind_speed_10m" in str(params["hourly"])
    assert "precipitation" in str(params["hourly"])
    assert "snowfall" in str(params["hourly"])


def test_multi_location_comma_separated_lists():
    params = forecast_query_params_multi(
        [19.07, 18.52, 21.15],
        [72.88, 73.86, 79.09],
        forecast_hours=48,
    )
    assert params["latitude"] == "19.07000,18.52000,21.15000"
    assert params["longitude"] == "72.88000,73.86000,79.09000"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["forecast_hours"] == 48
    assert "forecast_days" not in params


def test_snowfall_cm_converted_to_inches():
    hourly = {
        "time": ["2026-06-01T00:00", "2026-06-01T01:00"],
        "wind_speed_10m": [10.0, 20.0],  # already mph when unit param set
        "precipitation": [0.1, 0.2],  # already inches
        "snowfall": [2.54, 5.08],  # cm from API
    }
    parsed = parse_hourly_payload(hourly)
    assert parsed.wind_mph == [10.0, 20.0]
    assert parsed.precip_in == [0.1, 0.2]
    assert parsed.snow_in[0] == cm_to_inches(2.54)
    assert parsed.snow_in[1] == cm_to_inches(5.08)
    assert abs(parsed.snow_in[0] - 1.0) < 1e-9
    assert abs(parsed.snow_in[1] - 2.0) < 1e-9


def test_parse_handles_nulls_and_empty():
    parsed = parse_hourly_payload(
        {
            "time": ["2026-01-01T00:00"],
            "wind_speed_10m": [None],
            "precipitation": [None],
            "snowfall": [None],
        }
    )
    assert parsed.wind_mph == [0.0]
    assert parsed.precip_in == [0.0]
    assert parsed.snow_in == [0.0]
