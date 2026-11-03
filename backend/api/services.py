"""
Orchestration: geocode → route → checkpoints → weather@ETA → risk → recommend.

This is the only module that ties providers to core logic. Views stay thin.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
from django.conf import settings

from api.providers import geocoding, routing, weather
from core.checkpoints import sample_checkpoints
from core.corridor import corridor_grid_points
from core.eta import etas_along_route, to_local
from core.open_meteo import HOURLY_HORIZON
from core.recommend import (
    RouteRiskSummary,
    average_risk,
    build_miles_by_level,
    forward_segment_miles,
    recommend,
)
from core.risk import RISK_LABELS, WeatherSample, classify_checkpoint, classify_checkpoint_explained
from core.units import meters_to_miles


def _parse_departure(value: str) -> datetime:
    """Accept ISO-8601; naive values are treated as UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _timing(label: str, t0: float) -> None:
    if settings.DEBUG:
        ms = (time.perf_counter() - t0) * 1000.0
        print(f"[timing] {label}: {ms:.0f} ms", flush=True)


def _heatmap_payload(
    *,
    grid_lnglat: list[tuple[float, float]],
    series_list: list[weather.HourlySeries],
    load_lb: float,
    use_demo: bool,
    mid_lat: float,
    mid_lng: float,
    storm_peak: int,
    hours: int = HOURLY_HORIZON,
) -> dict[str, Any]:
    """Build corridor heatmap from grid points + already-fetched hourly series."""
    hours = max(1, min(HOURLY_HORIZON, hours))
    time_axis: list[str] = []
    if series_list and series_list[0].times:
        time_axis = list(series_list[0].times[:hours])

    points_out: list[dict[str, Any]] = []
    for (lng, lat), series in zip(grid_lnglat, series_list):
        wx = series
        if use_demo:
            wx = weather.apply_demo_storm(
                series,
                storm_lat=mid_lat + 0.35,
                storm_lng=mid_lng - 0.15,
                peak_hour=storm_peak,
            )
        risk_hours: list[int] = []
        for h in range(hours):
            if h >= len(wx.wind_mph):
                risk_hours.append(1)
                continue
            sample = WeatherSample(
                wind_mph=wx.wind_mph[h],
                precip_in_hr=wx.precip_in[h],
                snow_in_hr=wx.snow_in[h],
            )
            risk_hours.append(int(classify_checkpoint(sample, load_lb)))
        points_out.append({"coordinates": [lng, lat], "risk": risk_hours})

    if grid_lnglat:
        lngs = [lng for lng, _ in grid_lnglat]
        lats = [lat for _, lat in grid_lnglat]
        pad = 0.15
        bbox = [
            min(lngs) - pad,
            min(lats) - pad,
            max(lngs) + pad,
            max(lats) + pad,
        ]
    else:
        bbox = [mid_lng - 0.5, mid_lat - 0.5, mid_lng + 0.5, mid_lat + 0.5]

    return {
        "bbox": bbox,
        "hours": hours,
        "times_utc": time_axis,
        "coordinate_order": "lng,lat",
        "buffer_km": 20,
        "demo_storm": use_demo,
        "points": points_out,
    }


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
    t_all = time.perf_counter()

    with httpx.Client(timeout=90.0) as client:
        t0 = time.perf_counter()
        origin, dest = geocoding.geocode_pair(origin_query, destination_query)
        _timing("geocode (parallel)", t0)

        origin_ll = (origin.lng, origin.lat)
        dest_ll = (dest.lng, dest.lat)

        t0 = time.perf_counter()
        initial = routing.fetch_routes(origin_ll, dest_ll, alternatives=True, client=client)
        three = routing.ensure_three(origin_ll, dest_ll, initial, client=client)
        _timing("routing (3 routes)", t0)

        mid_lat = (origin.lat + dest.lat) / 2
        mid_lng = (origin.lng + dest.lng) / 2

        t0 = time.perf_counter()
        prepared: list[dict[str, Any]] = []
        checkpoint_points: list[tuple[float, float]] = []
        for idx, raw in enumerate(three):
            cps = sample_checkpoints(raw.geometry, interval_miles)
            etas = etas_along_route(
                cps,
                departure,
                total_duration_s=raw.duration_s,
                total_distance_m=raw.distance_m or 1.0,
            )
            prepared.append(
                {
                    "idx": idx,
                    "raw": raw,
                    "cps": cps,
                    "etas": etas,
                    "point_offset": len(checkpoint_points),
                }
            )
            checkpoint_points.extend((cp.lat, cp.lng) for cp in cps)

        polylines = [list(r.geometry) for r in three]
        grid_lnglat = corridor_grid_points(polylines)
        grid_weather_pts = [(lat, lng) for lng, lat in grid_lnglat]
        grid_offset = len(checkpoint_points)
        all_points = checkpoint_points + grid_weather_pts
        _timing(
            f"checkpoints+corridor grid ({len(checkpoint_points)} cp, {len(grid_lnglat)} grid)",
            t0,
        )

        t0 = time.perf_counter()
        series_all = weather.fetch_hourly_batch(all_points, client=client)
        _timing(f"open-meteo batch ({len(all_points)} pts)", t0)

        storm_peak = 8
        if use_demo and series_all:
            storm_peak = weather.peak_hour_for_departure(series_all[0], departure)

        t0 = time.perf_counter()
        route_payloads: list[dict[str, Any]] = []
        summaries: list[RouteRiskSummary] = []

        for item in prepared:
            idx = item["idx"]
            raw = item["raw"]
            cps = item["cps"]
            etas = item["etas"]
            offset = item["point_offset"]
            series_list = series_all[offset : offset + len(cps)]
            eta_by_idx = {e.checkpoint_index: e for e in etas}
            route_id = f"route-{idx}"

            checkpoint_rows = []
            levels = []

            for cp, series in zip(cps, series_list):
                if use_demo:
                    series = weather.apply_demo_storm(
                        series,
                        storm_lat=mid_lat + 0.55,
                        storm_lng=mid_lng,
                        peak_hour=storm_peak,
                    )
                eta = eta_by_idx[cp.index]
                sample = weather.sample_at_eta(series, eta.eta_utc)
                level, risk_reason = classify_checkpoint_explained(sample, load_lb)
                levels.append(level)

                checkpoint_rows.append(
                    {
                        "index": cp.index,
                        "lat": cp.lat,
                        "lng": cp.lng,
                        "distance_miles": round(meters_to_miles(cp.distance_m), 2),
                        "eta_utc": eta.eta_utc.isoformat(),
                        "eta_local": to_local(eta.eta_utc, display_tz).isoformat(),
                        "weather": {
                            "wind_mph": round(sample.wind_mph, 2),
                            "precip_in_hr": round(sample.precip_in_hr, 3),
                            "snow_in_hr": round(sample.snow_in_hr, 3),
                        },
                        "risk": RISK_LABELS[level],
                        "risk_score": int(level),
                        "risk_reason": risk_reason,
                    }
                )

            cumulative_mi = [meters_to_miles(cp.distance_m) for cp in cps]
            segment_miles = forward_segment_miles(cumulative_mi)
            for row, owned_mi in zip(checkpoint_rows, segment_miles):
                row["segment_miles"] = round(owned_mi, 2)

            miles_by = build_miles_by_level(levels, segment_miles)
            avg = average_risk(levels)
            display_label = f"Route {chr(ord('A') + idx)}"
            summary = RouteRiskSummary(
                route_id=route_id,
                label=display_label,
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
        _timing("risk + recommend", t0)

        t0 = time.perf_counter()
        grid_series = series_all[grid_offset : grid_offset + len(grid_lnglat)]
        heatmap = _heatmap_payload(
            grid_lnglat=grid_lnglat,
            series_list=grid_series,
            load_lb=load_lb,
            use_demo=use_demo,
            mid_lat=mid_lat,
            mid_lng=mid_lng,
            storm_peak=storm_peak,
        )
        _timing(f"heatmap assemble ({len(grid_lnglat)} pts × {HOURLY_HORIZON}h)", t0)
        _timing("analyze_routes total", t_all)

        return {
            "origin": {
                "query": origin_query,
                "lat": origin.lat,
                "lng": origin.lng,
                "label": origin.label,
            },
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
            "heatmap": heatmap,
        }


def build_heatmap(
    *,
    origin_query: str | None = None,
    destination_query: str | None = None,
    geometries: list[Any] | None = None,
    hours: int = 48,
    load_lb: float = 0.0,
    demo_storm: bool | None = None,
) -> dict[str, Any]:
    """
    Standalone heatmap (kept for the /weather/heatmap endpoint).

    Prefer the `heatmap` field on analyze_routes — one weather batch covers both.
    """
    use_demo = settings.DEMO_STORM if demo_storm is None else demo_storm
    hours = max(1, min(HOURLY_HORIZON, int(hours)))

    polylines: list[list[tuple[float, float]]] = []
    if geometries:
        for geom in geometries:
            line: list[tuple[float, float]] = []
            for pt in geom:
                if isinstance(pt, dict):
                    lng = float(pt["lng"] if "lng" in pt else pt["lon"])
                    lat = float(pt["lat"])
                else:
                    lng, lat = float(pt[0]), float(pt[1])
                line.append((lng, lat))
            if len(line) >= 2:
                polylines.append(line)

    with httpx.Client(timeout=90.0) as client:
        if len(polylines) < 1:
            if not origin_query or not destination_query:
                raise ValueError("provide geometries or origin+destination")
            origin, dest = geocoding.geocode_pair(origin_query, destination_query)
            origin_ll = (origin.lng, origin.lat)
            dest_ll = (dest.lng, dest.lat)
            initial = routing.fetch_routes(
                origin_ll, dest_ll, alternatives=True, client=client
            )
            three = routing.ensure_three(origin_ll, dest_ll, initial, client=client)
            polylines = [list(r.geometry) for r in three]
            mid_lat = (origin.lat + dest.lat) / 2
            mid_lng = (origin.lng + dest.lng) / 2
        else:
            all_lng = [lng for pl in polylines for lng, _ in pl]
            all_lat = [lat for pl in polylines for _, lat in pl]
            mid_lng = sum(all_lng) / len(all_lng)
            mid_lat = sum(all_lat) / len(all_lat)

        grid_lnglat = corridor_grid_points(polylines)
        weather_points = [(lat, lng) for lng, lat in grid_lnglat]
        series_list = weather.fetch_hourly_batch(weather_points, client=client)

        storm_peak = 8
        if use_demo and series_list:
            storm_peak = weather.peak_hour_for_departure(
                series_list[0], datetime.now(tz=timezone.utc)
            )

        return _heatmap_payload(
            grid_lnglat=grid_lnglat,
            series_list=series_list,
            load_lb=load_lb,
            use_demo=use_demo,
            mid_lat=mid_lat,
            mid_lng=mid_lng,
            storm_peak=storm_peak,
            hours=hours,
        )
