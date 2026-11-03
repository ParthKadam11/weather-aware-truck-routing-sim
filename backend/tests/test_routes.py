"""Route dedupe, via candidates, quality filters, Douglas–Peucker."""

from core.routes import (
    RawRoute,
    cell_set,
    dedupe_by_overlap,
    ensure_distinct_routes,
    ensure_three_routes,
    has_uturn,
    overlap_ratio,
    point_at_fraction,
    simplify_geometry,
    via_candidates,
    via_point_offsets,
)


def _route(dist: float, mid_lng: float = -87.0) -> RawRoute:
    return RawRoute(
        geometry=[(-88.0, 41.0), (mid_lng, 41.5), (-86.0, 42.0)],
        distance_m=dist,
        duration_s=dist / 20,
        label="",
    )


def test_dedupe_by_overlap_rejects_near_identical():
    a = _route(100_000, -87.0)
    b = _route(100_000, -87.0)
    assert len(dedupe_by_overlap([a, b])) == 1


def test_overlap_ratio_high_for_same_line():
    a = [(-88.0, 41.0), (-87.0, 41.5), (-86.0, 42.0)]
    b = [(-88.0, 41.0), (-87.0, 41.5), (-86.0, 42.0)]
    assert overlap_ratio(a, b) > 0.8


def test_overlap_ratio_low_for_shifted_line():
    a = [(-88.0, 41.0), (-87.0, 41.5), (-86.0, 42.0)]
    b = [(-88.0, 41.0), (-87.5, 40.0), (-86.0, 42.0)]
    assert overlap_ratio(a, b) < 0.8


def test_via_candidates_at_thirds_and_offsets():
    primary = _route(100_000)
    vias = via_candidates(primary)
    # 2 fractions × 2 sides × 3 distances
    assert len(vias) == 12
    assert len({(round(v[0], 4), round(v[1], 4)) for v in vias}) == 12


def test_via_point_offsets_returns_requested_count():
    primary = _route(100_000)
    vias = via_point_offsets(primary, count=2)
    assert len(vias) == 2
    assert vias[0] != vias[1]


def test_point_at_fraction_endpoints():
    geom = [(-88.0, 41.0), (-87.0, 41.0), (-86.0, 41.0)]
    assert point_at_fraction(geom, 0.0)[0] == -88.0
    assert abs(point_at_fraction(geom, 1.0)[0] - (-86.0)) < 1e-6


def test_has_uturn_detects_reverse():
    # Go east, then hard reverse west
    geom = [
        (0.0, 0.0),
        (0.05, 0.0),
        (0.10, 0.0),
        (0.05, 0.0),  # reverse
        (0.0, 0.0),
    ]
    assert has_uturn(geom) is True


def test_has_uturn_false_on_gentle_curve():
    geom = [(0.0, 0.0), (0.05, 0.0), (0.10, 0.02), (0.15, 0.05)]
    assert has_uturn(geom) is False


def test_simplify_geometry_reduces_points():
    # Dense straight line — DP should collapse to endpoints
    geom = [(i * 0.0001, 0.0) for i in range(100)]
    simple = simplify_geometry(geom, tolerance_m=50.0)
    assert len(simple) < len(geom)
    assert simple[0] == geom[0]
    assert simple[-1] == geom[-1]


def test_cell_set_snaps():
    cells = cell_set([(1.0001, 2.0001), (1.0002, 2.0002)])
    assert len(cells) == 1


def test_ensure_distinct_fetches_via_when_short():
    primary = _route(100_000, -87.0)
    calls = {"n": 0}

    def fetch_batch(vias):
        out = []
        for via in vias:
            calls["n"] += 1
            lng, lat = via
            out.append(
                RawRoute(
                    geometry=[(-88.0, 41.0), (lng, lat), (-86.0, 42.0)],
                    distance_m=110_000 + calls["n"] * 5_000,
                    duration_s=5000 + calls["n"],
                    label=f"via-{calls['n']}",
                    via_points=[via],
                )
            )
            if len([x for x in out if x]) >= 2:
                # Return rest as None to stop early enough after merge
                break
        # Pad to len(vias)
        while len(out) < len(vias):
            out.append(None)
        return out

    result = ensure_distinct_routes([primary], fetch_via_batch=fetch_batch)
    assert 2 <= len(result.routes) <= 3
    assert calls["n"] >= 1
    assert all(r.label.startswith("Route ") for r in result.routes)


def test_ensure_never_clones_when_fetch_fails():
    primary = _route(100_000)

    def fetch_batch(_vias):
        return [None] * len(_vias)

    result = ensure_distinct_routes([primary], fetch_via_batch=fetch_batch)
    assert len(result.routes) == 1
    assert result.note
    assert "only 1" in result.note.lower()
    assert "clone" in result.note.lower() or "distinct" in result.note.lower()


def test_ensure_three_routes_compat_no_clone():
    primary = _route(100_000)

    def fetch_via(_via):
        return None

    result = ensure_three_routes([primary], fetch_via_route=fetch_via)
    assert len(result) == 1
