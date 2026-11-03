"""Checkpoint sampling along a polyline."""

import pytest

from core.checkpoints import sample_checkpoints
from core.units import miles_to_meters


def _eastbound_line(miles: float, steps: int = 20) -> list[tuple[float, float]]:
    """Rough eastbound line from (0, 0) spanning ~`miles` (lng increases)."""
    # 1 deg lng at equator ≈ 69.17 mi
    total_deg = miles / 69.17
    return [(i * total_deg / steps, 0.0) for i in range(steps + 1)]


def test_rejects_bad_interval():
    with pytest.raises(ValueError):
        sample_checkpoints(_eastbound_line(100), interval_miles=15)


def test_rejects_short_geometry():
    with pytest.raises(ValueError):
        sample_checkpoints([(0.0, 0.0)], interval_miles=10)


def test_includes_origin_and_destination():
    coords = _eastbound_line(100)
    cps = sample_checkpoints(coords, interval_miles=25)
    assert cps[0].distance_m == 0.0
    assert cps[0].lat == 0.0
    # Last is destination
    assert cps[-1].lng == coords[-1][0]
    assert cps[-1].lat == coords[-1][1]


def test_spacing_approximately_interval():
    coords = _eastbound_line(100)
    cps = sample_checkpoints(coords, interval_miles=25)
    # Interior checkpoints (excluding dest if not on a multiple) should be ~25 mi apart
    interval_m = miles_to_meters(25)
    for i in range(1, len(cps) - 1):
        assert cps[i].distance_m == pytest.approx(i * interval_m, rel=0.02)


def test_10_mile_interval_more_checkpoints_than_50():
    coords = _eastbound_line(100)
    c10 = sample_checkpoints(coords, interval_miles=10)
    c50 = sample_checkpoints(coords, interval_miles=50)
    assert len(c10) > len(c50)
