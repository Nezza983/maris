"""
processing.py
-------------
Everything between "raw inputs" and "a clean dict of candidate vessel
trajectories": loading Module 4's output, loading and validating AIS
data (synthetic or real - this file does not know or care which), and
spatial/temporal filtering.

None of the functions here hard-code the spill location or time window -
those always come from the Module 4 JSON passed in by the caller.
"""

from __future__ import annotations

import json
import warnings
from datetime import timedelta
from typing import Dict

import numpy as np
import pandas as pd

from module5_ais.config import Module5Config, DEFAULT_CONFIG
from module5_ais.geo_utils import haversine_km_vec

REQUIRED_AIS_COLUMNS = [
    "mmsi",
    "vessel_name",
    "timestamp",
    "latitude",
    "longitude",
    "sog",
    "cog",
    "heading",
]


# ---------------------------------------------------------------------------
# Module 4 input
# ---------------------------------------------------------------------------


def load_module4_output(path: str) -> dict:
    """
    Load and lightly validate Module 4's origin_zone / time_window JSON.
    Raises ValueError with a clear message if the expected keys are
    missing, rather than failing later with a confusing KeyError deep in
    the scoring code.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "origin_zone" not in data or "time_window" not in data:
        raise ValueError(
            f"Module 4 output at {path} is missing 'origin_zone' or "
            "'time_window'. Got keys: " + ", ".join(data.keys())
        )

    origin_zone = data["origin_zone"]
    if origin_zone.get("type") != "circle":
        raise ValueError(
            "Module 5 currently only supports origin_zone.type == 'circle'. "
            f"Got: {origin_zone.get('type')!r}"
        )
    if "center" not in origin_zone or "radius_km" not in origin_zone:
        raise ValueError("origin_zone must contain 'center' and 'radius_km'.")

    tw = data["time_window"]
    if "start" not in tw or "end" not in tw:
        raise ValueError("time_window must contain 'start' and 'end'.")

    return data


def _to_utc_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")


def parse_time_window(module4_output: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Parse Module 4's time window strings into UTC-aware pandas Timestamps."""
    start = _to_utc_timestamp(module4_output["time_window"]["start"])
    end = _to_utc_timestamp(module4_output["time_window"]["end"])
    return start, end


# ---------------------------------------------------------------------------
# AIS loading / validation
# ---------------------------------------------------------------------------


def load_ais_csv(path: str) -> pd.DataFrame:
    """
    Load an AIS CSV (synthetic or real - same schema either way) and
    return a cleaned, validated, sorted DataFrame.

    This is the ONLY function that needs to change if the real AIS
    source has a different raw format (e.g. real feeds sometimes use
    'MMSI', 'BaseDateTime', 'LAT', 'LON', 'SOG', 'COG', 'Heading' -
    normalise that in a thin adapter and still hand this function the
    standard column names).

    Invalid rows are dropped with an explicit, printed count - never
    silently discarded without a trace.
    """
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_AIS_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"AIS file {path} is missing required column(s): {missing}. "
            f"Required columns are: {REQUIRED_AIS_COLUMNS}"
        )

    n_start = len(df)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    n_bad_ts = df["timestamp"].isna().sum()
    df = df.dropna(subset=["timestamp"])

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    valid_coords = (
        df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)
    )
    n_bad_coords = (~valid_coords).sum()
    df = df[valid_coords]

    df["sog"] = pd.to_numeric(df["sog"], errors="coerce")
    valid_sog = df["sog"].between(0, 60)  # 60 kn is a generous upper bound for any vessel
    n_bad_sog = (~valid_sog).sum()
    df = df[valid_sog]

    df["cog"] = pd.to_numeric(df["cog"], errors="coerce")
    df["heading"] = pd.to_numeric(df["heading"], errors="coerce")
    # cog/heading of 360 or NaN ("not available", AIS spec code 511 maps to
    # NaN after numeric coercion of non-numeric sentinels) are tolerated -
    # they simply won't contribute to trajectory-heading calculations for
    # that single point.
    df.loc[~df["cog"].between(0, 360), "cog"] = np.nan
    df.loc[~df["heading"].between(0, 360), "heading"] = np.nan

    df["mmsi"] = df["mmsi"].astype(str)
    df["vessel_name"] = df["vessel_name"].astype(str)

    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    n_dropped = n_start - len(df)
    if n_dropped > 0:
        warnings.warn(
            f"load_ais_csv: dropped {n_dropped} of {n_start} rows from {path} "
            f"(bad timestamp: {n_bad_ts}, bad coordinates: {n_bad_coords}, "
            f"bad sog: {n_bad_sog})."
        )

    if df.empty:
        raise ValueError(f"AIS file {path} contained no valid rows after cleaning.")

    return df


# ---------------------------------------------------------------------------
# Spatial filtering
# ---------------------------------------------------------------------------


def spatial_filter(
    df: pd.DataFrame, origin_zone: dict, config: Module5Config = DEFAULT_CONFIG
) -> pd.DataFrame:
    """
    Keep only AIS records within origin_zone.radius_km * config.spatial_filter_factor
    of the origin center, using proper haversine great-circle distance
    (not raw lat/lon differencing, which distorts distance at this
    latitude).

    The filter radius is deliberately wider than the origin radius
    itself: a vessel might be a genuinely weak candidate (and should be
    SCORED low) without being so far away that it should be excluded from
    consideration entirely. Scoring, not filtering, is where "far away"
    gets penalised.
    """
    center_lat, center_lon = origin_zone["center"]
    radius_km = origin_zone["radius_km"]
    cutoff_km = radius_km * config.spatial_filter_factor

    distances = haversine_km_vec(
        df["latitude"].to_numpy(), df["longitude"].to_numpy(), center_lat, center_lon
    )
    out = df.copy()
    out["distance_to_origin_km"] = distances
    return out[out["distance_to_origin_km"] <= cutoff_km].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Temporal filtering
# ---------------------------------------------------------------------------


def temporal_filter(
    df: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    config: Module5Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """
    Keep only AIS records within [window_start - buffer, window_end + buffer].

    The buffer exists because Module 4's time-window estimate comes from
    a drift/backtracking model, not a measured fact - it will have some
    error. A hard cutoff at the exact window would risk dropping the
    real source vessel just because the estimated origin time was off by
    an hour. config.time_buffer_hours is the tunable "how much do we
    trust Module 4's timing" knob; widen it if Module 4 reports large
    uncertainty, narrow it if the estimate is tight.
    """
    buffer = timedelta(hours=config.time_buffer_hours)
    lo = window_start - buffer
    hi = window_end + buffer
    return df[(df["timestamp"] >= lo) & (df["timestamp"] <= hi)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------


def extract_candidates(
    df: pd.DataFrame, config: Module5Config = DEFAULT_CONFIG
) -> Dict[str, pd.DataFrame]:
    """
    Group filtered AIS records by vessel (mmsi) and drop any vessel that
    doesn't have enough points to form a meaningful trajectory. Returns a
    dict of mmsi -> DataFrame (sorted by timestamp, original columns and
    values preserved untouched).
    """
    candidates: Dict[str, pd.DataFrame] = {}
    for mmsi, group in df.groupby("mmsi"):
        if len(group) < config.min_trajectory_points:
            continue
        candidates[mmsi] = group.sort_values("timestamp").reset_index(drop=True)
    return candidates
