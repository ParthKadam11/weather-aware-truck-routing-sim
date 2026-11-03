"""
Orchestration: geocode → route → checkpoints → weather@ETA → risk → recommend.

This is the only module that ties providers to core logic. Views stay thin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from django.conf import settings

from api.providers import geocoding, routing, weather
from core.checkpoints import sample_checkpoints
from core.eta import etas_along_route, to_local
from core.recommend import (
    RouteRiskSummary,
    average_risk,
    build_miles_by_level,
    recommend,
)
from core.risk import RISK_LABELS, classify_checkpoint
from core.units import meters_to_miles


def _parse_departure(value: str) -> datetime:
    """Accept ISO-8601; naive values are treated as UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def analyze_routes(
    *,
    origin_query: str,
    destination_query: str,
    departure_iso: str,
    load_lb: float,
    interval_miles: int,
    display_tz: str | None = None,
    demo_storm: bool | None = None,
) -> dict[str, Any]:
    display_tz = display_tz or settings.DEFAULT_DISPLAY_TZ
    departure = _parse_departure(departure_iso)
    use_demo = settings.DEMO_STORM if demo_storm is None else demo_storm

    with httpx.Client(timeout=45.0) as client:
        origin = geocoding.geocode(origin_query, client=client)
        dest = geocoding.geocode(destination_query, client=client)

        origin_ll = (origin.lng, origin.lat)
        dest_ll = (dest.lng, dest.lat)

        initial = routing.fetch_routes(origin_ll, dest_ll, alternatives=True, client=client)
        three = routing.ensure_three(origin_ll, dest_ll, initial, client=client)

        # Corridor midpoint for demo storm placement
        mid_lat = (origin.lat + dest.lat) / 2
        mid_lng = (origin.lng + dest.lng) / 2

        route_payloads: list[dict[str, Any]] = []
        summaries: list[RouteRiskSummary] = []

        for idx, raw in enumerate(three):
            route_id = f"route-{idx}"
            cps = sample_checkpoints(raw.geometry, interval_miles)
            etas = etas_along_route(
                cps,
                departure,
                total_duration_s=raw.duration_s,
                total_distance_m=raw.distance_m or 1.0,
            )
            eta_by_idx = {e.checkpoint_index: e for e in etas}

            points = [(cp.lat, cp.lng) for cp in cps]
            series_list = weather.fetch_hourly_batch(points, forecast_days=3, client=client)

            checkpoint_rows = []
            levels = []
            segment_miles = []

            storm_peak = 8
            if use_demo and series_list:
                storm_peak = weather.peak_hour_for_departure(series_list[0], departure)

            for cp, series in zip(cps, series_list):
                if use_demo:
                    # Offset north of the corridor so northern alts catch more storm
                    series = weather.apply_demo_storm(
                        series,
                        storm_lat=mid_lat + 0.55,
                        storm_lng=mid_lng,
                        peak_hour=storm_peak,
                    )
                eta = eta_by_idx[cp.index]
                sample = weather.sample_at_eta(series, eta.eta_utc)
                level = classify_checkpoint(sample, load_lb)
                levels.append(level)
                segment_miles.append(meters_to_miles(cp.segment_m))

                checkpoint_rows.append(
                    {
                        "index": cp.index,
                        "lat": cp.lat,
                        "lng": cp.lng,
                        "distance_miles": round(meters_to_miles(cp.distance_m), 2),
                        "segment_miles": round(meters_to_miles(cp.segment_m), 2),
                        "eta_utc": eta.eta_utc.isoformat(),
                        "eta_local": to_local(eta.eta_utc, display_tz).isoformat(),
                        "weather": {
                            "wind_mph": round(sample.wind_mph, 2),
                            "precip_in_hr": round(sample.precip_in_hr, 3),
                            "snow_in_hr": round(sample.snow_in_hr, 3),
                        },
                        "risk": RISK_LABELS[level],
                        "risk_score": int(level),
                    }
                )

            miles_by = build_miles_by_level(levels, segment_miles)
            avg = average_risk(levels)
            summary = RouteRiskSummary(
                route_id=route_id,
                label=raw.label or f"Route {chr(ord('A') + idx)}",
                duration_s=raw.duration_s,
                distance_m=raw.distance_m,
                miles_by_level=miles_by,
                average_risk=avg,
                checkpoint_count=len(cps),
            )
            summaries.append(summary)

            route_payloads.append(
                {
                    "id": route_id,
                    "label": summary.label,
                    "distance_miles": round(meters_to_miles(raw.distance_m), 2),
                    "duration_s": raw.duration_s,
                    "duration_hours": round(raw.duration_s / 3600, 2),
                    "geometry": [{"lng": lng, "lat": lat} for lng, lat in raw.geometry],
                    "checkpoints": checkpoint_rows,
                    "miles_by_risk": {
                        RISK_LABELS[k]: round(v, 2) for k, v in miles_by.items()
                    },
                    "average_risk": round(avg, 3),
                }
            )

        rec = recommend(summaries)
        for rp in route_payloads:
            rp["recommended"] = rp["id"] == rec.route_id
            rp["rank"] = rec.ranked_ids.index(rp["id"]) + 1

        return {
            "origin": {"query": origin_query, "lat": origin.lat, "lng": origin.lng, "label": origin.label},
            "destination": {
                "query": destination_query,
                "lat": dest.lat,
                "lng": dest.lng,
                "label": dest.label,
            },
            "departure_utc": departure.isoformat(),
            "load_lb": load_lb,
            "interval_miles": interval_miles,
            "display_tz": display_tz,
            "demo_storm": use_demo,
            "recommendation": {
                "route_id": rec.route_id,
                "reason": rec.reason,
                "ranked_ids": rec.ranked_ids,
            },
            "routes": route_payloads,
        }


def build_heatmap(
    *,
    origin_query: str,
    destination_query: str,
    hours: int = 48,
    grid_step_deg: float = 0.28,
    demo_storm: bool | None = None,
) -> dict[str, Any]:
    """
    Fetch a full 0–`hours` weather grid once over the route corridor bbox.
    Frontend slides frames client-side with no further network calls.
    """
    use_demo = settings.DEMO_STORM if demo_storm is None else demo_storm
    hours = max(1, min(48, hours))

    with httpx.Client(timeout=60.0) as client:
        origin = geocoding.geocode(origin_query, client=client)
        dest = geocoding.geocode(destination_query, client=client)

        # Pad corridor; denser default step suits shorter state routes (e.g. MH)
        pad = 0.55
        min_lat = min(origin.lat, dest.lat) - pad
        max_lat = max(origin.lat, dest.lat) + pad
        min_lng = min(origin.lng, dest.lng) - pad
        max_lng = max(origin.lng, dest.lng) + pad

        mid_lat = (origin.lat + dest.lat) / 2
        mid_lng = (origin.lng + dest.lng) / 2

        def _build_grid(step: float) -> tuple[list[float], list[float]]:
            out_lats: list[float] = []
            out_lngs: list[float] = []
            lat = min_lat
            while lat <= max_lat + 1e-9:
                lng = min_lng
                while lng <= max_lng + 1e-9:
                    out_lats.append(round(lat, 3))
                    out_lngs.append(round(lng, 3))
                    lng += step
                lat += step
            return out_lats, out_lngs

        lats, lngs = _build_grid(grid_step_deg)
        # Cap grid size for free-API friendliness
        step = grid_step_deg
        while len(lats) > 64 and step < 1.2:
            step *= 1.35
            lats, lngs = _build_grid(step)

        points = list(zip(lats, lngs))
        series_list = weather.fetch_hourly_batch(
            points, forecast_days=max(3, (hours // 24) + 1), client=client
        )

        frames: list[dict[str, Any]] = []
        time_axis = series_list[0].times[:hours] if series_list else []

        storm_peak = 8
        if use_demo and series_list:
            # Align bloom near "now" so the 0–48h slider shows change quickly
            storm_peak = weather.peak_hour_for_departure(
                series_list[0],
                datetime.now(tz=timezone.utc),
            )

        for h in range(min(hours, len(time_axis) or hours)):
            cells = []
            for series in series_list:
                wx = series
                if use_demo:
                    wx = weather.apply_demo_storm(
                        series,
                        storm_lat=mid_lat + 0.35,
                        storm_lng=mid_lng - 0.15,
                        peak_hour=storm_peak,
                    )
                if h >= len(wx.wind_mph):
                    continue
                wind = wx.wind_mph[h]
                precip = wx.precip_in[h]
                snow = wx.snow_in[h]
                # Keep a visible floor so calm cells still tint lightly
                intensity = min(
                    1.0,
                    max(0.08, wind / 45.0, precip / 0.8, snow / 2.5),
                )
                cells.append(
                    {
                        "lat": wx.lat,
                        "lng": wx.lng,
                        "wind_mph": round(wind, 2),
                        "precip_in": round(precip, 3),
                        "snow_in": round(snow, 3),
                        "intensity": round(intensity, 3),
                    }
                )
            frames.append(
                {
                    "hour": h,
                    "time_utc": time_axis[h] if h < len(time_axis) else None,
                    "cells": cells,
                }
            )

        return {
            "bbox": [min_lng, min_lat, max_lng, max_lat],
            "hours": len(frames),
            "demo_storm": use_demo,
            "frames": frames,
        }
