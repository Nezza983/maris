"""
Module 3 — Ocean Current Fetcher (CMEMS)

Fetches sea surface current components (uo, vo) from the Copernicus Marine
Global Analysis/Forecast Physics product for a given location and time.

Dataset: cmems_mod_glo_phy_anfc_0.083deg_PT1H-m
Resolution: ~0.083° (~9 km), hourly
Variables: uo (eastward current), vo (northward current) at surface (depth=0)
Units: m/s

Requires CMEMS credentials (register at https://data.marine.copernicus.eu/register).
"""

import pandas as pd
import numpy as np
from datetime import timedelta

try:
    import copernicusmarine
except ImportError:
    copernicusmarine = None


DATASET_ID = "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"
BUFFER_DEG = 0.5  # spatial box half-width around the query point (degrees)
TEMPORAL_WINDOW_HOURS = 3  # ± hours around the target time


def get_currents(
    lat: float,
    lon: float,
    time_str: str,
    username: str,
    password: str,
    buffer: float = BUFFER_DEG,
) -> tuple[float, float]:
    """
    Return (current_u, current_v) in m/s at the ocean surface for the given
    point and time.

    Parameters
    ----------
    lat : float
        Latitude in degrees (south is negative).
    lon : float
        Longitude in degrees (east is positive).
    time_str : str
        ISO 8601 timestamp, e.g. "2022-07-15T06:00:00".
    username : str
        CMEMS account email.
    password : str
        CMEMS account password.
    buffer : float
        Half-width of the spatial bounding box in degrees (default 0.5°).

    Returns
    -------
    tuple[float, float]
        (u, v) surface current in m/s.  Positive u = eastward, positive v = northward.

    Raises
    ------
    ImportError
        If the ``copernicusmarine`` package is not installed.
    Exception
        If the API call fails (auth error, out-of-range date, etc.).
    """
    if copernicusmarine is None:
        raise ImportError(
            "Install copernicusmarine: pip install copernicusmarine"
        )

    t = pd.Timestamp(time_str)

    # If the timestamp is timezone-naive, assume UTC
    if t.tzinfo is None:
        t = t.tz_localize("UTC")

    ds = copernicusmarine.open_dataset(
        dataset_id=DATASET_ID,
        minimum_longitude=lon - buffer,
        maximum_longitude=lon + buffer,
        minimum_latitude=lat - buffer,
        maximum_latitude=lat + buffer,
        start_datetime=(t - timedelta(hours=TEMPORAL_WINDOW_HOURS)).isoformat(),
        end_datetime=(t + timedelta(hours=TEMPORAL_WINDOW_HOURS)).isoformat(),
        username=username,
        password=password,
    )

    # Interpolate to the exact point and time
    point = ds.interp(
        latitude=lat,
        longitude=lon,
        time=t,
        method="linear",
    )

    # Select the surface layer (first depth index) if depth dimension exists
    if "depth" in point.dims:
        point = point.isel(depth=0)

    u = float(point["uo"].values)
    v = float(point["vo"].values)

    # Validate output
    if np.isnan(u) or np.isnan(v):
        raise ValueError(
            f"Interpolated current values are NaN at ({lat}, {lon}, {time_str}). "
            "The point may be over land or outside the dataset time range."
        )

    return u, v
