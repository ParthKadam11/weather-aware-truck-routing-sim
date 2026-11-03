"""ETA and forecast-hour indexing."""

from datetime import datetime, timezone

from core.checkpoints import Checkpoint
from core.eta import etas_along_route, forecast_hour_index, to_local


def test_etas_scale_with_distance():
    cps = [
        Checkpoint(0, 0, 0, 0.0, 0.0),
        Checkpoint(1, 0, 1, 50_000.0, 50_000.0),
        Checkpoint(2, 0, 2, 100_000.0, 50_000.0),
    ]
    dep = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    etas = etas_along_route(cps, dep, total_duration_s=7200, total_distance_m=100_000)
    assert etas[0].eta_utc == dep
    assert etas[1].duration_from_start_s == 3600
    assert etas[2].duration_from_start_s == 7200


def test_naive_departure_treated_as_utc():
    cps = [Checkpoint(0, 0, 0, 0.0, 0.0), Checkpoint(1, 0, 1, 10.0, 10.0)]
    dep = datetime(2026, 1, 1, 8, 0)  # naive
    etas = etas_along_route(cps, dep, total_duration_s=100, total_distance_m=10)
    assert etas[0].eta_utc.tzinfo == timezone.utc


def test_to_local_america_chicago():
    utc = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)
    local = to_local(utc, "America/Chicago")
    # CST = UTC-6 in January
    assert local.hour == 12


def test_forecast_hour_index():
    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    eta = datetime(2026, 6, 1, 5, 30, tzinfo=timezone.utc)
    assert forecast_hour_index(eta, start) == 5
    # Before start clamps to 0
    early = datetime(2026, 5, 31, 20, 0, tzinfo=timezone.utc)
    assert forecast_hour_index(early, start) == 0
