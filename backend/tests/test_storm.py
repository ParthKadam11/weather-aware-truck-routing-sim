"""Demo StormConfig — shared by analyze + heatmap; on vs off changes totals."""

from datetime import datetime, timezone

from core.recommend import average_risk, build_miles_by_level, forward_segment_miles
from core.risk import RiskLevel, WeatherSample, classify_checkpoint
from core.storm import (
    StormConfig,
    apply_storm_arrays,
    build_storm_config,
    departure_hour_index,
)


def test_storm_wind_rain_only_no_floor_no_snow():
    storm = StormConfig(lat=19.0, lng=73.0, radius_deg=0.3, peak_hour=2)
    wind0 = [8.0] * 12
    rain0 = [0.0] * 12
    snow0 = [0.1] * 12
    wind, rain, snow = apply_storm_arrays(
        lat=19.0,
        lng=73.0,
        wind_mph=wind0,
        precip_in=rain0,
        snow_in=snow0,
        storm=storm,
    )
    assert snow == snow0
    # Additive boost at peak — not a max() floor against 18 mph
    assert wind[2] == wind0[2] + storm.wind_boost_mph
    assert rain[2] == rain0[2] + storm.rain_boost_in
    # Outside radius → unchanged
    far_w, far_r, _ = apply_storm_arrays(
        lat=21.0,
        lng=75.0,
        wind_mph=wind0,
        precip_in=rain0,
        snow_in=snow0,
        storm=storm,
    )
    assert far_w == wind0
    assert far_r == rain0


def test_build_storm_peaks_1_to_2h_after_departure():
    line = [(72.8, 19.0), (73.0, 19.05), (73.2, 19.1)]
    times = [f"2026-11-03T{h:02d}:00" for h in range(24)]
    departure = datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc)
    storm = build_storm_config(
        [line],
        departure_utc=departure,
        forecast_times=times,
        peak_offset_h=2,
    )
    dep_idx = departure_hour_index(times, departure)
    assert storm.peak_hour == dep_idx + 2
    assert storm.radius_deg == 0.3
    mid_lng, mid_lat = line[len(line) // 2]
    assert abs(storm.lat - mid_lat) > 0.05 or abs(storm.lng - mid_lng) > 0.05


def test_storm_on_vs_off_gives_different_route_totals():
    """Same calm checkpoint weather: storm on near the route raises risk totals."""
    cps = [
        (19.00, 72.90),
        (19.05, 73.00),
        (19.10, 73.10),
    ]
    cumulative_mi = [0.0, 25.0, 50.0]
    segment_miles = forward_segment_miles(cumulative_mi)
    load_lb = 40_000.0

    storm = StormConfig(
        lat=19.05 + 0.12,
        lng=73.00,
        radius_deg=0.3,
        peak_hour=2,
    )

    def totals(*, storm_on: bool) -> tuple[float, dict[RiskLevel, float]]:
        levels = []
        for lat, lng in cps:
            wind = [8.0] * 12
            rain = [0.0] * 12
            snow = [0.0] * 12
            if storm_on:
                wind, rain, snow = apply_storm_arrays(
                    lat=lat,
                    lng=lng,
                    wind_mph=wind,
                    precip_in=rain,
                    snow_in=snow,
                    storm=storm,
                )
            sample = WeatherSample(
                wind_mph=wind[2],
                precip_in_hr=rain[2],
                snow_in_hr=snow[2],
            )
            levels.append(classify_checkpoint(sample, load_lb))
        miles = build_miles_by_level(levels, segment_miles)
        return average_risk(levels), miles

    avg_off, miles_off = totals(storm_on=False)
    avg_on, miles_on = totals(storm_on=True)

    assert avg_on > avg_off
    severe_on = miles_on[RiskLevel.SEVERE] + miles_on[RiskLevel.NO_TRAVEL]
    severe_off = miles_off[RiskLevel.SEVERE] + miles_off[RiskLevel.NO_TRAVEL]
    assert severe_on > severe_off or avg_on >= avg_off + 0.5
