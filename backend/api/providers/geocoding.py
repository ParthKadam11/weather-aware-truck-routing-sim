"""Geocoding via Photon (Komoot) with Nominatim fallback — free, no API key."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache

import httpx
from django.conf import settings


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lng: float
    label: str


class GeocodingError(Exception):
    pass


USER_AGENT = "WeatherAwareTruckRouting/1.0 (assessment; contact=local-dev)"


def _photon(query: str, client: httpx.Client) -> GeoResult | None:
    url = f"{settings.PHOTON_BASE_URL.rstrip('/')}/api/"
    resp = client.get(
        url,
        params={"q": query, "limit": 1},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if resp.status_code >= 400:
        return None
    features = (resp.json() or {}).get("features") or []
    if not features:
        return None
    feat = features[0]
    coords = feat["geometry"]["coordinates"]  # [lng, lat]
    props = feat.get("properties") or {}
    parts = [
        props.get("name"),
        props.get("city") or props.get("county"),
        props.get("state"),
        props.get("country"),
    ]
    label = ", ".join(p for p in parts if p) or query
    return GeoResult(lat=float(coords[1]), lng=float(coords[0]), label=label)


def _nominatim(query: str, client: httpx.Client) -> GeoResult | None:
    url = "https://nominatim.openstreetmap.org/search"
    resp = client.get(
        url,
        params={"q": query, "format": "json", "limit": 1},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if resp.status_code >= 400:
        return None
    rows = resp.json() or []
    if not rows:
        return None
    row = rows[0]
    return GeoResult(
        lat=float(row["lat"]),
        lng=float(row["lon"]),
        label=row.get("display_name") or query,
    )


def _geocode_uncached(query: str) -> GeoResult:
    with httpx.Client(timeout=20.0) as client:
        result = _photon(query, client) or _nominatim(query, client)
        if result is None:
            raise GeocodingError(f"no results for '{query}'")
        return result


@lru_cache(maxsize=256)
def _geocode_cached(query: str) -> GeoResult:
    """LRU-cached geocode by normalized query string."""
    return _geocode_uncached(query)


def geocode(query: str, *, client: httpx.Client | None = None) -> GeoResult:
    """
    Resolve a free-text place name / address to lat/lng.

    Uses an LRU cache. `client` is accepted for API compatibility but ignored
    when serving from cache / dedicated request clients.
    """
    del client  # each lookup uses its own short-lived client (thread-safe)
    query = query.strip()
    if not query:
        raise GeocodingError("empty geocode query")
    try:
        return _geocode_cached(query)
    except httpx.HTTPError as exc:
        raise GeocodingError(f"geocoding failed: {exc}") from exc


def geocode_pair(origin_query: str, destination_query: str) -> tuple[GeoResult, GeoResult]:
    """Geocode origin and destination in parallel."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_origin = pool.submit(geocode, origin_query)
        f_dest = pool.submit(geocode, destination_query)
        return f_origin.result(), f_dest.result()
