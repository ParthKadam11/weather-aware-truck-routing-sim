from core.units import cm_to_inches, meters_to_miles, miles_to_meters, ms_to_mph


def test_cm_to_inches():
    assert cm_to_inches(2.54) == 1.0
    assert abs(cm_to_inches(10.0) - 3.937) < 0.01


def test_ms_to_mph():
    assert abs(ms_to_mph(10.0) - 22.369) < 0.01


def test_miles_meters_roundtrip():
    assert abs(meters_to_miles(miles_to_meters(25)) - 25) < 1e-9
