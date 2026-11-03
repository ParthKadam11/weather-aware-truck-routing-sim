"""Unit conversions used by weather providers and risk scoring."""

CM_PER_INCH = 2.54


def cm_to_inches(cm: float) -> float:
    """Convert centimeters to inches."""
    return cm / CM_PER_INCH


def ms_to_mph(ms: float) -> float:
    """Convert meters/second to miles/hour (Open-Meteo default wind unit)."""
    return ms * 2.2369362921


def meters_to_miles(meters: float) -> float:
    return meters / 1609.344


def miles_to_meters(miles: float) -> float:
    return miles * 1609.344
