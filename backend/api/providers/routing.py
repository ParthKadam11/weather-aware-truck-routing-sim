"""OSRM public routing — alternatives=3, nearest snap, parallel via fetches."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Sequence

import httpx
from django.conf import settings

from core.routes import RawRoute, RouteSetResult, ensure_distinct_routes


class RoutingError(Exception):
    pass


def _decode_polyline(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    """Decode Google-encoded polyline to (lng, lat) pairs."""
    coordinates: list[tuple[float, float]] = []
    index, lat, lng = 0, 0, 0
    factor = 10**precision

    while index < len(encoded):
        result = shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += dlat

        result = shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else (result >> 1)
        lng += dlng

        coordinates.append((lng / factor, lat / factor))

    return coordinates


def _parse_route(route: dict, label: str = "") -> RawRoute:
    geometry = route.get("geometry")
    if isinstance(geometry, str):
        coords = _decode_polyline(geometry)
    elif isinstance(geometry, dict) and geometry.get("coordinates"):
        coords = [(c[0], c[1]) for c in geometry["coordinates"]]
    else:
        coords = []
    return RawRoute(
        geometry=coords,
        distance_m=float(route["distance"]),
        duration_s=float(route["duration"]),
        label=label,
    )


def fetch_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    alternatives: int | bool = 3,
    client: httpx.Client | None = None,
) -> list[RawRoute]:
    """
    origin/destination as (lng, lat).

    Requests OSRM `alternatives=3` (or bool/int as given).
    """
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        coords = f"{origin[0]},{origin[1]};{destination[0]},{destination[1]}"
        url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coords}"
        if isinstance(alternatives, bool):
            alt_param: str | int = "true" if alternatives else "false"
        else:
            alt_param = max(0, int(alternatives))
        params = {
            "overview": "full",
            "geometries": "polyline",
            "alternatives": alt_param,
            "steps": "false",
        }
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RoutingError(f"OSRM error: {data.get('code', 'unknown')}")
        routes = []
        for i, r in enumerate(data["routes"]):
            routes.append(_parse_route(r, label=f"Route {chr(ord('A') + i)}"))
        return routes
    except httpx.HTTPError as exc:
        raise RoutingError(f"routing failed: {exc}") from exc
    finally:
        if owns:
            client.close()


def nearest_point(
    lng: float,
    lat: float,
    *,
    client: httpx.Client | None = None,
) -> tuple[float, float] | None:
    """Snap (lng, lat) to the nearest drivability graph node via OSRM /nearest."""
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        url = f"{settings.OSRM_BASE_URL.rstrip('/')}/nearest/v1/driving/{lng},{lat}"
        resp = client.get(url, params={"number": 1})
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            return None
        waypoints = data.get("waypoints") or []
        if not waypoints:
            return None
        loc = waypoints[0].get("location")
        if not loc or len(loc) < 2:
            return None
        return (float(loc[0]), float(loc[1]))  # GeoJSON lng, lat
    except httpx.HTTPError:
        return None
    finally:
        if owns:
            client.close()


def fetch_route_via(
    origin: tuple[float, float],
    via: tuple[float, float],
    destination: tuple[float, float],
    *,
    client: httpx.Client | None = None,
) -> RawRoute | None:
    """Single route forced through a via-point. Returns None on failure."""
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        coords = (
            f"{origin[0]},{origin[1]};{via[0]},{via[1]};{destination[0]},{destination[1]}"
        )
        url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coords}"
        params = {
            "overview": "full",
            "geometries": "polyline",
            "alternatives": "false",
            "steps": "false",
        }
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = _parse_route(data["routes"][0], label="Via alternative")
        route.via_points = [via]
        return route
    except httpx.HTTPError:
        return None
    finally:
        if owns:
            client.close()


def _snap_and_route(
    origin: tuple[float, float],
    via: tuple[float, float],
    destination: tuple[float, float],
) -> RawRoute | None:
    """Own httpx client per worker — snap via with /nearest, then route."""
    with httpx.Client(timeout=30.0) as client:
        snapped = nearest_point(via[0], via[1], client=client) or via
        return fetch_route_via(origin, snapped, destination, client=client)


def fetch_via_batch_parallel(
    origin: tuple[float, float],
    destination: tuple[float, float],
    vias: Sequence[tuple[float, float]],
    *,
    max_workers: int = 8,
) -> list[RawRoute | None]:
    """Snap each via + fetch route in parallel; preserve candidate order."""
    if not vias:
        return []
    results: list[RawRoute | None] = [None] * len(vias)
    workers = min(max_workers, len(vias))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_snap_and_route, origin, via, destination): i
            for i, via in enumerate(vias)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception:
                results[i] = None
    return results


def ensure_three(
    origin: tuple[float, float],
    destination: tuple[float, float],
    initial: Sequence[RawRoute],
    *,
    client: httpx.Client | None = None,
) -> RouteSetResult:
    """
    Build up to 3 distinct routes. Never clones.

    Returns RouteSetResult(routes, note) — note explains when fewer than 3.
    """
    del client  # workers own clients for parallel via search

    def fetch_batch(vias: Sequence[tuple[float, float]]) -> list[RawRoute | None]:
        return fetch_via_batch_parallel(origin, destination, vias)

    return ensure_distinct_routes(initial, fetch_via_batch=fetch_batch)
