"""OSRM public routing — alternatives + via-point fetches."""

from __future__ import annotations

from typing import Sequence

import httpx
from django.conf import settings

from core.routes import RawRoute


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
    alternatives: bool = True,
    client: httpx.Client | None = None,
) -> list[RawRoute]:
    """
    origin/destination as (lng, lat).
    Uses OSRM `alternatives=true` when available.
    """
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        coords = f"{origin[0]},{origin[1]};{destination[0]},{destination[1]}"
        url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coords}"
        params = {
            "overview": "full",
            "geometries": "polyline",
            "alternatives": "true" if alternatives else "false",
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
        return _parse_route(data["routes"][0], label="Via alternative")
    except httpx.HTTPError:
        return None
    finally:
        if owns:
            client.close()


def ensure_three(
    origin: tuple[float, float],
    destination: tuple[float, float],
    initial: Sequence[RawRoute],
    *,
    client: httpx.Client | None = None,
) -> list[RawRoute]:
    from core.routes import ensure_three_routes

    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:

        def fetch_via(via: tuple[float, float]) -> RawRoute | None:
            return fetch_route_via(origin, via, destination, client=client)

        return ensure_three_routes(initial, fetch_via_route=fetch_via)
    finally:
        if owns:
            client.close()
