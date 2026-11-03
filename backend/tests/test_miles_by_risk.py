"""Forward segment ownership and risk-bucket totals vs route length."""

from core.checkpoints import sample_checkpoints
from core.recommend import (
    build_miles_by_level,
    forward_segment_miles,
    total_miles,
)
from core.risk import RiskLevel
from core.units import meters_to_miles, miles_to_meters


def test_forward_segment_miles_owns_until_next():
    # Checkpoints at 0, 25, 50, 80 mi → own 25, 25, 30, 0
    owned = forward_segment_miles([0.0, 25.0, 50.0, 80.0])
    assert owned == [25.0, 25.0, 30.0, 0.0]
    assert sum(owned) == 80.0


def test_forward_segments_sum_to_route_length():
    # Eastbound ~100 mi polyline
    total_deg = 100 / 69.17
    coords = [(i * total_deg / 40, 0.0) for i in range(41)]
    cps = sample_checkpoints(coords, interval_miles=25)
    cumulative = [meters_to_miles(cp.distance_m) for cp in cps]
    owned = forward_segment_miles(cumulative)

    assert owned[-1] == 0.0
    assert len(owned) == len(cps)
    # Every non-last ownership equals gap to next cumulative distance
    for i in range(len(cps) - 1):
        assert owned[i] == cumulative[i + 1] - cumulative[i]

    route_len = cumulative[-1]
    assert abs(sum(owned) - route_len) < 1e-9


def test_miles_by_level_buckets_sum_to_route_length():
    levels = [
        RiskLevel.LOW,
        RiskLevel.MODERATE,
        RiskLevel.HIGH,
        RiskLevel.SEVERE,
        RiskLevel.NO_TRAVEL,
    ]
    # Forward segments including trailing 0 for last checkpoint
    segments = [10.0, 20.0, 15.0, 5.0, 0.0]
    route_length = 50.0
    assert sum(segments) == route_length

    buckets = build_miles_by_level(levels, segments)
    assert abs(total_miles(buckets) - route_length) < 1e-9
    assert buckets[RiskLevel.LOW] == 10.0
    assert buckets[RiskLevel.MODERATE] == 20.0
    assert buckets[RiskLevel.HIGH] == 15.0
    assert buckets[RiskLevel.SEVERE] == 5.0
    assert buckets[RiskLevel.NO_TRAVEL] == 0.0


def test_last_checkpoint_owns_zero_miles():
    levels = [RiskLevel.LOW, RiskLevel.HIGH]
    segments = forward_segment_miles([0.0, 42.0])
    assert segments == [42.0, 0.0]
    buckets = build_miles_by_level(levels, segments)
    assert buckets[RiskLevel.LOW] == 42.0
    assert buckets[RiskLevel.HIGH] == 0.0
    assert total_miles(buckets) == 42.0


def test_sampled_route_bucket_total_matches_last_distance():
    """End-to-end: sample → forward miles → buckets ≡ route length."""
    # ~75 mile line
    length_mi = 75.0
    total_deg = length_mi / 69.17
    coords = [(i * total_deg / 30, 0.0) for i in range(31)]
    cps = sample_checkpoints(coords, interval_miles=25)
    cumulative = [meters_to_miles(c.distance_m) for c in cps]
    segments = forward_segment_miles(cumulative)
    # Alternate risk levels
    levels = [
        RiskLevel.LOW if i % 2 == 0 else RiskLevel.SEVERE for i in range(len(cps))
    ]
    buckets = build_miles_by_level(levels, segments)
    assert abs(total_miles(buckets) - cumulative[-1]) < 1e-6
    # Also close to nominal polyline length (haversine ≈ planned miles)
    assert abs(cumulative[-1] - length_mi) < 2.0
