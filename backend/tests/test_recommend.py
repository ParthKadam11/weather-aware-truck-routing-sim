"""Recommendation ranking order and reason text."""

from core.recommend import (
    RouteRiskSummary,
    average_risk,
    build_miles_by_level,
    recommend,
    sort_key,
)
from core.risk import RiskLevel


def _summary(
    route_id: str,
    *,
    severe: float = 0,
    no_travel: float = 0,
    high: float = 0,
    moderate: float = 0,
    low: float = 100,
    avg: float = 1.0,
    duration_s: float = 3600,
) -> RouteRiskSummary:
    return RouteRiskSummary(
        route_id=route_id,
        label=route_id,
        duration_s=duration_s,
        distance_m=100_000,
        miles_by_level={
            RiskLevel.LOW: low,
            RiskLevel.MODERATE: moderate,
            RiskLevel.HIGH: high,
            RiskLevel.SEVERE: severe,
            RiskLevel.NO_TRAVEL: no_travel,
        },
        average_risk=avg,
    )


def test_prefer_fewest_severe_plus_no_travel():
    a = _summary("A", severe=20, high=0, avg=2.0, duration_s=5000)
    b = _summary("B", severe=5, high=40, avg=3.0, duration_s=8000)
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert "severe" in rec.reason.lower()


def test_no_travel_counts_with_severe():
    a = _summary("A", severe=0, no_travel=15)
    b = _summary("B", severe=10, no_travel=0)
    # A has more severe+NT miles (15 > 10)
    assert sort_key(a)[0] == 15
    assert sort_key(b)[0] == 10
    assert recommend([a, b]).route_id == "B"


def test_tiebreak_fewest_high():
    a = _summary("A", severe=10, high=30, avg=2.5, duration_s=1000)
    b = _summary("B", severe=10, high=5, avg=2.5, duration_s=9000)
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert "high" in rec.reason.lower()


def test_tiebreak_average_risk():
    a = _summary("A", severe=0, high=0, avg=2.8, duration_s=1000)
    b = _summary("B", severe=0, high=0, avg=1.5, duration_s=9000)
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert "average risk" in rec.reason.lower()


def test_tiebreak_shortest_time():
    a = _summary("A", severe=0, high=0, avg=2.0, duration_s=8000)
    b = _summary("B", severe=0, high=0, avg=2.0, duration_s=4000)
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert "shortest" in rec.reason.lower()


def test_build_miles_by_level():
    # Forward segments: last checkpoint may own 0
    levels = [RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.SEVERE]
    miles = [10.0, 20.0, 0.0]
    result = build_miles_by_level(levels, miles)
    assert result[RiskLevel.LOW] == 10.0
    assert result[RiskLevel.HIGH] == 20.0
    assert result[RiskLevel.SEVERE] == 0.0
    assert result[RiskLevel.MODERATE] == 0.0
    assert sum(result.values()) == 30.0


def test_average_risk():
    assert average_risk([RiskLevel.LOW, RiskLevel.SEVERE]) == 2.5
