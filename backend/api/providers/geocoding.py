"""Geocoding via Photon (Komoot) with Nominatim fallback — free, no API key."""

from __future__ import annotations

from dataclasses import dataclass

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


def geocode(query: str, *, client: httpx.Client | None = None) -> GeoResult:
    """
    Resolve a free-text place name / address to lat/lng.

    Tries Photon first; falls back to Nominatim (requires a User-Agent).
    """
    query = query.strip()
    if not query:
        raise GeocodingError("empty geocode query")

    owns_client = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        result = _photon(query, client) or _nominatim(query, client)
        if result is None:
            raise GeocodingError(f"no results for '{query}'")
        return result
    except httpx.HTTPError as exc:
        raise GeocodingError(f"geocoding failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()
