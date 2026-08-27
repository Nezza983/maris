"""
Module 3 — Wind Data Fetcher (ERA5 / CDS)

Fetches 10-metre u- and v-wind components from the ECMWF ERA5 reanalysis
via the Copernicus Climate Data Store (CDS) API.

Dataset: reanalysis-era5-single-levels
Variables: 10m_u_component_of_wind (u10), 10m_v_component_of_wind (v10)
Units: m/s

Requires a CDS account and API key (register at https://cds.climate.copernicus.eu).
You must also accept the ERA5 Terms of Use once on the CDS website before API
calls will work.
"""

import os
import pandas as pd
import numpy as np

try:
    import cdsapi
except ImportError:
    cdsapi = None

try:
    import xarray as xr
except ImportError:
    xr = None


CDS_URL = "https://cds.climate.copernicus.eu/api"
ERA5_DATASET = "reanalysis-era5-single-levels"
BUFFER_DEG = 0.5  # spatial box half-width around the query point (degrees)


def get_wind(
    lat: float,
    lon: float,
    time_str: str,
    cds_key: str,
    buffer: float = BUFFER_DEG,
) -> tuple[float, float]:
    """
    Return (wind_u, wind_v) in m/s at 10 m height for the given point/time.

    Parameters
    ----------
    lat : float
        Latitude in degrees (south is negative).
    lon : float
        Longitude in degrees (east is positive).
    time_str : str
        ISO 8601 timestamp, e.g. "2022-07-15T06:00:00".
    cds_key : str
        CDS API key (from https://cds.climate.copernicus.eu/profile).
    buffer : float
        Half-width of the spatial bounding box in degrees (default 0.5°).

    Returns
    -------
    tuple[float, float]
        (u, v) wind at 10 m in m/s.  Positive u = eastward, positive v = northward.

    Raises
    ------
    ImportError
        If ``cdsapi`` or ``xarray`` packages are not installed.
    Exception
        If the CDS API call fails (licence not accepted, auth error, etc.).
    """
    if cdsapi is None:
        raise ImportError("Install cdsapi: pip install cdsapi")
    if xr is None:
        raise ImportError("Install xarray: pip install xarray netCDF4")

    t = pd.Timestamp(time_str)

    if t.tzinfo is not None:
        t = t.tz_localize(None)  # CDS expects naive UTC

    target = "era5_wind_tmp.nc"

    client = cdsapi.Client(url=CDS_URL, key=cds_key)

    client.retrieve(
        ERA5_DATASET,
        {
            "product_type": "reanalysis",
            "variable": [
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
            ],
            "year": f"{t.year}",
            "month": f"{t.month:02d}",
            "day": f"{t.day:02d}",
            "time": f"{t.hour:02d}:00",
            "area": [
                lat + buffer,   # North
                lon - buffer,   # West
                lat - buffer,   # South
                lon + buffer,   # East
            ],
            "data_format": "netcdf",
        },
        target,
    )

    ds = xr.open_dataset(target)

    point = ds.interp(
        latitude=lat,
        longitude=lon,
        method="linear",
    )

    u = float(point["u10"].values)
    v = float(point["v10"].values)

    # Clean up temp file
    try:
        os.remove(target)
    except OSError:
        pass

    # Validate output
    if np.isnan(u) or np.isnan(v):
        raise ValueError(
            f"Interpolated wind values are NaN at ({lat}, {lon}, {time_str})."
        )

    return u, v
