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
    forward_segment_miles,
    recommend,
)
from core.risk import RISK_LABELS, classify_checkpoint_explained
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

        # --- Pass 1: sample checkpoints + ETAs for all 3 routes ---
        prepared: list[dict[str, Any]] = []
        all_points: list[tuple[float, float]] = []
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
                    "point_offset": len(all_points),
                }
            )
            all_points.extend((cp.lat, cp.lng) for cp in cps)

        # --- ONE Open-Meteo multi-location request (48h) for every checkpoint ---
        series_all = weather.fetch_hourly_batch(all_points, client=client)

        storm_peak = 8
        if use_demo and series_all:
            storm_peak = weather.peak_hour_for_departure(series_all[0], departure)

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
                # Pick forecast hour by ETA; cached on rounded lat/lng + hour
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


def _normalize_polylines(
    geometries: list[Any] | None,
) -> list[list[tuple[float, float]]]:
    """
    Accept route geometries as [{lng, lat}, ...] or [[lng, lat], ...].
    Always returns GeoJSON-ordered (lng, lat) tuples.
    """
    if not geometries:
        return []
    out: list[list[tuple[float, float]]] = []
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
            out.append(line)
    return out


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
    Corridor weather grid: points ONLY within ~30 km of the 3 route polylines.

    One Open-Meteo batch; each point carries 48 hourly risk scores (1–5).
    Coordinates are GeoJSON [lng, lat]. Frontend picks weight for the selected hour.
    """
    from core.corridor import corridor_grid_points
    from core.open_meteo import HOURLY_HORIZON
    from core.risk import WeatherSample, classify_checkpoint

    use_demo = settings.DEMO_STORM if demo_storm is None else demo_storm
    hours = max(1, min(HOURLY_HORIZON, int(hours)))

    with httpx.Client(timeout=90.0) as client:
        polylines = _normalize_polylines(geometries)

        if len(polylines) < 1:
            if not origin_query or not destination_query:
                raise ValueError("provide geometries or origin+destination")
            origin = geocoding.geocode(origin_query, client=client)
            dest = geocoding.geocode(destination_query, client=client)
            origin_ll = (origin.lng, origin.lat)
            dest_ll = (dest.lng, dest.lat)
            initial = routing.fetch_routes(
                origin_ll, dest_ll, alternatives=True, client=client
            )
            three = routing.ensure_three(
                origin_ll, dest_ll, initial, client=client
            )
            polylines = [list(r.geometry) for r in three]  # already (lng, lat)

        # Midpoint for demo storm (lng/lat careful)
        all_lng = [lng for pl in polylines for lng, _ in pl]
        all_lat = [lat for pl in polylines for _, lat in pl]
        mid_lng = sum(all_lng) / len(all_lng)
        mid_lat = sum(all_lat) / len(all_lat)

        # Grid in GeoJSON (lng, lat), clipped to 30 km buffer
        grid_lnglat = corridor_grid_points(polylines)
        # Weather batch expects (lat, lng) tuples
        weather_points = [(lat, lng) for lng, lat in grid_lnglat]

        series_list = weather.fetch_hourly_batch(weather_points, client=client)

        storm_peak = 8
        if use_demo and series_list:
            storm_peak = weather.peak_hour_for_departure(
                series_list[0],
                datetime.now(tz=timezone.utc),
            )

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
                level = classify_checkpoint(sample, load_lb)
                risk_hours.append(int(level))
            points_out.append(
                {
                    # GeoJSON position: [longitude, latitude]
                    "coordinates": [lng, lat],
                    "risk": risk_hours,
                }
            )

        min_lng, min_lat = min(all_lng), min(all_lat)
        max_lng, max_lat = max(all_lng), max(all_lat)
        # Pad bbox ~30 km for the map
        pad = 0.3
        return {
            "bbox": [min_lng - pad, min_lat - pad, max_lng + pad, max_lat + pad],
            "hours": hours,
            "times_utc": time_axis,
            "coordinate_order": "lng,lat",
            "buffer_km": 30,
            "demo_storm": use_demo,
            "points": points_out,
        }
