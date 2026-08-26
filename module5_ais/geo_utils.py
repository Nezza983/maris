"""
geo_utils.py
------------
Small shared geographic helpers. Both processing.py (spatial filtering)
and scoring.py (distance / trajectory scoring) need "distance between two
lat/lon points" and "bearing between two lat/lon points", so this lives in
one place instead of being duplicated (and potentially drifting out of
sync) in two files.
"""

import math

import numpy as np

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two points in kilometres.

    We use haversine (not flat-earth lat/lon differencing) because at this
    project's scale (tens of km near the Indian coast) a naive
    sqrt(dlat^2 + dlon^2) comparison is measurably wrong: degrees of
    longitude shrink in real distance as latitude increases, so comparing
    raw coordinate differences would bias distance scoring depending on
    which latitude the spill happens to be at.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def haversine_km_vec(
    lat1: np.ndarray, lon1: np.ndarray, lat2: float, lon2: float
) -> np.ndarray:
    """
    Vectorised haversine: distance from an array of points to a single
    fixed point (the origin zone center). Used by spatial_filter() in
    processing.py so we don't call the scalar haversine_km() in a slow
    Python-level DataFrame.apply() loop over every AIS record.
    """
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)

    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Initial compass bearing (0-360 degrees, 0 = north) from point 1 to
    point 2. Used to compare "direction a vessel would need to travel to
    reach the origin" against its actual reported course over ground.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        dlambda
    )
    theta = math.atan2(x, y)
    return (math.degrees(theta) + 360) % 360


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two compass angles (0-180)."""
    d = abs(a - b) % 360
    return min(d, 360 - d)
