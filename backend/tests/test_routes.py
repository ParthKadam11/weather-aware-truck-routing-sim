"""Route dedupe and ensure-three behavior."""

from core.routes import RawRoute, dedupe_routes, ensure_three_routes, via_point_offsets


def _route(dist: float, mid_lng: float = -87.0) -> RawRoute:
    return RawRoute(
        geometry=[(-88.0, 41.0), (mid_lng, 41.5), (-86.0, 42.0)],
        distance_m=dist,
        duration_s=dist / 20,
        label="",
    )


def test_dedupe_identical_signatures():
    a = _route(100_000, -87.0)
    b = _route(100_000, -87.0)
    assert len(dedupe_routes([a, b])) == 1


def test_dedupe_keeps_different_mids():
    a = _route(100_000, -87.0)
    b = _route(100_000, -87.5)
    assert len(dedupe_routes([a, b])) == 2


def test_via_point_offsets_returns_requested_count():
    primary = _route(100_000)
    vias = via_point_offsets(primary, count=2)
    assert len(vias) == 2
    assert vias[0] != vias[1]


def test_ensure_three_fetches_via_when_short():
    primary = _route(100_000, -87.0)
    calls = {"n": 0}

    def fetch_via(via):
        calls["n"] += 1
        # Return a route with a shifted midpoint so it doesn't dedupe
        lng, lat = via
        return RawRoute(
            geometry=[(-88.0, 41.0), (lng, lat), (-86.0, 42.0)],
            distance_m=110_000 + calls["n"] * 1000,
            duration_s=5000 + calls["n"],
            label=f"via-{calls['n']}",
        )

    result = ensure_three_routes([primary], fetch_via_route=fetch_via)
    assert len(result) == 3
    assert calls["n"] >= 2


def test_ensure_three_pads_when_fetch_fails():
    primary = _route(100_000)

    def fetch_via(_via):
        return None

    result = ensure_three_routes([primary], fetch_via_route=fetch_via)
    assert len(result) == 3
    assert "limited alternatives" in result[1].label.lower() or result[1].label
