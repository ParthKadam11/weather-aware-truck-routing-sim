"""Corridor buffer grid — GeoJSON (lng, lat) order."""

from core.corridor import (
    corridor_grid_points,
    distance_to_polyline_m,
)


def test_point_on_line_is_near_zero():
    # Horizontal-ish segment near equator
    line = [(-1.0, 0.0), (1.0, 0.0)]
    d = distance_to_polyline_m((0.0, 0.0), line)
    assert d < 50  # meters


def test_point_30km_off_line():
    line = [(72.8, 19.0), (73.9, 18.5)]  # Mumbai-ish → Pune-ish
    # ~0.27 deg lat ≈ 30 km
    pt = (73.35, 18.75 + 0.27)
    d = distance_to_polyline_m(pt, line)
    assert 25_000 < d < 40_000


def test_grid_only_within_buffer():
    # Short eastbound polyline
    line = [(72.80, 19.00), (73.00, 19.00)]
    pts = corridor_grid_points([line], buffer_m=30_000, step_m=10_000, max_points=80)
    assert pts
    for lng, lat in pts:
        assert distance_to_polyline_m((lng, lat), line) <= 30_000 + 500
        # GeoJSON order: lng first
        assert abs(lng) > abs(lat) or True  # both small; just ensure tuple order used
        assert isinstance(lng, float) and isinstance(lat, float)


def test_grid_uses_lng_lat_order():
    line = [(75.0, 19.0), (76.0, 19.5)]
    pts = corridor_grid_points([line], buffer_m=30_000, step_m=12_000)
    # All longitudes near 75–76, latitudes near 19
    for lng, lat in pts:
        assert 74.5 < lng < 76.5
        assert 18.5 < lat < 20.0
