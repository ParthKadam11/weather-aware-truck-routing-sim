"""Route ranking and plain-English recommendation reasons."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.risk import RISK_LABELS, RiskLevel


@dataclass
class RouteRiskSummary:
    """Aggregated risk stats for one route option."""

    route_id: str
    label: str
    duration_s: float
    distance_m: float
    miles_by_level: dict[RiskLevel, float] = field(default_factory=dict)
    average_risk: float = 0.0
    checkpoint_count: int = 0


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    reason: str
    ranked_ids: list[str]


def miles_for(summary: RouteRiskSummary, *levels: RiskLevel) -> float:
    return sum(summary.miles_by_level.get(level, 0.0) for level in levels)


def sort_key(summary: RouteRiskSummary) -> tuple:
    """
    Prefer (ascending):
      1. Fewest Severe + No Travel miles
      2. Fewest High miles
      3. Lowest average risk
      4. Shortest travel time
    """
    severe_plus = miles_for(summary, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)
    high = miles_for(summary, RiskLevel.HIGH)
    return (severe_plus, high, summary.average_risk, summary.duration_s)


def recommend(routes: Sequence[RouteRiskSummary]) -> Recommendation:
    if not routes:
        raise ValueError("no routes to recommend")

    ranked = sorted(routes, key=sort_key)
    best = ranked[0]
    reason = _reason(best, ranked)
    return Recommendation(
        route_id=best.route_id,
        reason=reason,
        ranked_ids=[r.route_id for r in ranked],
    )


def _reason(best: RouteRiskSummary, ranked: Sequence[RouteRiskSummary]) -> str:
    severe = miles_for(best, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)
    high = miles_for(best, RiskLevel.HIGH)
    others = [r for r in ranked if r.route_id != best.route_id]

    if not others:
        return (
            f"{best.label} is the only option "
            f"({severe:.0f} mi severe/no-travel, avg risk {best.average_risk:.2f})."
        )

    second = others[0]
    s_severe = miles_for(second, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)
    s_high = miles_for(second, RiskLevel.HIGH)

    if severe < s_severe - 0.01:
        return (
            f"{best.label} is recommended because it has the fewest severe/no-travel "
            f"miles ({severe:.0f} mi vs {s_severe:.0f} mi on {second.label})."
        )
    if high < s_high - 0.01:
        return (
            f"{best.label} is recommended because, with similar severe miles, "
            f"it has fewer high-risk miles ({high:.0f} mi vs {s_high:.0f} mi "
            f"on {second.label})."
        )
    if best.average_risk < second.average_risk - 0.001:
        return (
            f"{best.label} is recommended for the lowest average risk "
            f"({best.average_risk:.2f} vs {second.average_risk:.2f} on {second.label})."
        )
    hours = best.duration_s / 3600
    other_hours = second.duration_s / 3600
    return (
        f"{best.label} is recommended as the shortest option among similarly risky "
        f"routes ({hours:.1f} h vs {other_hours:.1f} h on {second.label})."
    )


def build_miles_by_level(
    checkpoint_levels: Sequence[RiskLevel],
    segment_miles: Sequence[float],
) -> dict[RiskLevel, float]:
    """
    Attribute each segment's miles to the risk of the checkpoint at its end
    (weather encountered when arriving at that point).
    """
    if len(checkpoint_levels) != len(segment_miles):
        raise ValueError("levels and segment_miles length mismatch")

    miles: dict[RiskLevel, float] = {level: 0.0 for level in RiskLevel}
    for level, mi in zip(checkpoint_levels, segment_miles):
        miles[level] = miles.get(level, 0.0) + mi
    return miles


def average_risk(checkpoint_levels: Sequence[RiskLevel]) -> float:
    if not checkpoint_levels:
        return float(RiskLevel.LOW)
    return sum(int(level) for level in checkpoint_levels) / len(checkpoint_levels)


def level_label(level: RiskLevel) -> str:
    return RISK_LABELS[level]
