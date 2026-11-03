"""Corridor along-track samples — GeoJSON (lng, lat) order."""

from core.corridor import (
    DEFAULT_SNAP_DEG,
    corridor_grid_points,
    distance_to_polyline_m,
)


def test_point_on_line_is_near_zero():
    line = [(-1.0, 0.0), (1.0, 0.0)]
    d = distance_to_polyline_m((0.0, 0.0), line)
    assert d < 50


def test_point_30km_off_line():
    line = [(72.8, 19.0), (73.9, 18.5)]
    pt = (73.35, 18.75 + 0.27)
    d = distance_to_polyline_m(pt, line)
    assert 25_000 < d < 40_000


def test_grid_uses_lng_lat_order():
    line = [(75.0, 19.0), (76.0, 19.5)]
    pts = corridor_grid_points([line])
    assert pts
    for lng, lat in pts:
        assert 74.0 < lng < 77.0
        assert 18.0 < lat < 21.0


def test_grid_snaps_and_dedupes():
    line = [(72.80, 19.00), (73.00, 19.00)]
    pts = corridor_grid_points([line], step_m=8_000, snap_deg=DEFAULT_SNAP_DEG)
    assert pts
    assert len(pts) == len(set(pts))
    for lng, lat in pts:
        assert abs(lng / DEFAULT_SNAP_DEG - round(lng / DEFAULT_SNAP_DEG)) < 1e-6
        assert abs(lat / DEFAULT_SNAP_DEG - round(lat / DEFAULT_SNAP_DEG)) < 1e-6


def test_grid_includes_perpendicular_offsets():
    # Eastbound ~24 km so multiple center samples
    line = [(72.80, 19.00), (73.02, 19.00)]
    pts = corridor_grid_points([line], step_m=8_000, offsets_m=(10_000.0, 20_000.0))
    lats = [lat for _, lat in pts]
    # Offsets north/south of the 19° centerline after snap
    assert max(lats) - min(lats) > 0.15
