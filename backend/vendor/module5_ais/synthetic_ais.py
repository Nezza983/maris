"""
synthetic_ais.py
----------------
Generates a SYNTHETIC AIS dataset for development, testing and demoing
Module 5 before real (or real-looking) AIS access is available.

This file is intentionally the ONLY place that knows the data is fake.
processing.py and scoring.py just consume a CSV with the standard AIS
schema and have no idea whether it came from here, from a real AIS
provider's export, or from AISstream/GFW. That separation is the whole
point: swapping synthetic data for real data later means pointing
main.py at a different CSV path, not touching any processing/scoring code.

Design of the demo scenario (all relative to the mock Module 4 output in
data/sample/mock_module4_output.json: origin at (14.50, 74.85), radius
15 km, time window 2026-08-20T10:00-18:00 UTC):

  Vessel A (strong candidate) - transits directly through the origin
    zone during the estimated time window, reports normally.
  Vessel B (wrong time)       - passes near the origin, but well before
    the time window starts.
  Vessel C (wrong location)   - active during the correct time window,
    but stays far from the origin.
  Vessel D (anomalous)        - transits near the origin during the
    correct window, but has a long AIS reporting gap and an abrupt
    course/speed change.
  Background vessels          - ordinary traffic scattered around the
    wider area, present at various times, meant to rank below A/D.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from module5_ais.geo_utils import bearing_deg

AIS_COLUMNS = [
    "mmsi",
    "vessel_name",
    "timestamp",
    "latitude",
    "longitude",
    "sog",
    "cog",
    "heading",
]


def _km_to_deg_lat(km: float) -> float:
    return km / 110.574


def _km_to_deg_lon(km: float, at_lat_deg: float) -> float:
    return km / (111.320 * max(np.cos(np.radians(at_lat_deg)), 1e-6))


def _straight_track(
    mmsi: str,
    vessel_name: str,
    start_latlon: tuple[float, float],
    end_latlon: tuple[float, float],
    start_time: datetime,
    n_points: int,
    interval_minutes: float,
    speed_knots: float,
    rng: np.random.Generator,
    position_noise_km: float = 0.15,
    speed_noise_knots: float = 0.5,
    drop_indices: set[int] | None = None,
) -> pd.DataFrame:
    """
    Build one vessel's AIS track as a straight-line interpolation between
    two points, evenly spaced in time, with small realistic noise added
    to position/speed and course-over-ground derived from the bearing
    between consecutive points.

    A straight-line interpolation is a deliberate simplification: it is
    NOT meant to model realistic ship maneuvering physics, only to give
    the scoring pipeline plausible position/speed/course sequences to
    work with. drop_indices lets the caller simulate an AIS reporting gap
    by removing rows from the otherwise-regular sequence.
    """
    drop_indices = drop_indices or set()
    lats = np.linspace(start_latlon[0], end_latlon[0], n_points)
    lons = np.linspace(start_latlon[1], end_latlon[1], n_points)

    rows = []
    for i in range(n_points):
        if i in drop_indices:
            continue
        t = start_time + timedelta(minutes=interval_minutes * i)
        lat = lats[i] + rng.normal(0, _km_to_deg_lat(position_noise_km))
        lon = lons[i] + rng.normal(0, _km_to_deg_lon(position_noise_km, lats[i]))

        if i < n_points - 1:
            cog = bearing_deg(lats[i], lons[i], lats[i + 1], lons[i + 1])
        elif i > 0:
            cog = bearing_deg(lats[i - 1], lons[i - 1], lats[i], lons[i])
        else:
            cog = 0.0
        cog = (cog + rng.normal(0, 3)) % 360

        sog = max(0.1, speed_knots + rng.normal(0, speed_noise_knots))

        rows.append(
            {
                "mmsi": mmsi,
                "vessel_name": vessel_name,
                "timestamp": t.isoformat(),
                "latitude": round(float(lat), 6),
                "longitude": round(float(lon), 6),
                "sog": round(float(sog), 2),
                "cog": round(float(cog), 1),
                "heading": round(float(cog), 1),
            }
        )
    return pd.DataFrame(rows, columns=AIS_COLUMNS)


def generate_synthetic_ais(
    module4_output: dict, seed: int = 42
) -> pd.DataFrame:
    """
    Build the full synthetic AIS dataset (Vessels A-D + background
    vessels) around the given Module 4 origin_zone / time_window. Nothing
    here is hard-coded outside of this function's own scenario design -
    the origin/time values always come from module4_output.
    """
    rng = np.random.default_rng(seed)

    center_lat, center_lon = module4_output["origin_zone"]["center"]
    window_start = datetime.fromisoformat(
        module4_output["time_window"]["start"].replace("Z", "+00:00")
    )
    window_end = datetime.fromisoformat(
        module4_output["time_window"]["end"].replace("Z", "+00:00")
    )
    window_mid = window_start + (window_end - window_start) / 2

    tracks = []

    # --- Vessel A: strong candidate. Passes through the origin during
    # the window, on a clean 5-minute reporting cadence. ---
    a_start = window_mid - timedelta(hours=2)
    approach = (center_lat - _km_to_deg_lat(25), center_lon - _km_to_deg_lon(25, center_lat))
    depart = (center_lat + _km_to_deg_lat(20), center_lon + _km_to_deg_lon(20, center_lat))
    tracks.append(
        _straight_track(
            mmsi="419000001",
            vessel_name="MV KAVERI STAR",
            start_latlon=approach,
            end_latlon=depart,
            start_time=a_start,
            n_points=49,  # 4 hours at 5-min cadence
            interval_minutes=5,
            speed_knots=11.0,
            rng=rng,
        )
    )

    # --- Vessel B: wrong time. Passes close to the origin, but well
    # BEFORE the window opens. Its track ends at window_start - 1h, so
    # roughly the last hour of its track falls inside the default 2-hour
    # buffer (meaning it still survives temporal_filter() and gets
    # scored), while its overlap with the unbuffered window used by
    # time_score() is exactly zero - demonstrating a vessel that is
    # spatially plausible but clearly wrong-time. ---
    b_start = window_start - timedelta(hours=3)
    b_end_point = (center_lat + _km_to_deg_lat(5), center_lon - _km_to_deg_lon(10, center_lat))
    b_start_point = (center_lat - _km_to_deg_lat(30), center_lon - _km_to_deg_lon(35, center_lat))
    tracks.append(
        _straight_track(
            mmsi="419000002",
            vessel_name="MV COASTAL BREEZE",
            start_latlon=b_start_point,
            end_latlon=b_end_point,
            start_time=b_start,
            n_points=25,  # 2 hours at 5-min cadence
            interval_minutes=5,
            speed_knots=10.0,
            rng=rng,
        )
    )

    # --- Vessel C: wrong location. Active for the whole window, correct
    # timing, but stays roughly 35-40 km from the origin the whole time. ---
    c_start_point = (
        center_lat + _km_to_deg_lat(38),
        center_lon + _km_to_deg_lon(15, center_lat),
    )
    c_end_point = (
        center_lat + _km_to_deg_lat(35),
        center_lon + _km_to_deg_lon(28, center_lat),
    )
    tracks.append(
        _straight_track(
            mmsi="419000003",
            vessel_name="MV NORTHERN TRADER",
            start_latlon=c_start_point,
            end_latlon=c_end_point,
            start_time=window_start + timedelta(minutes=30),
            n_points=85,  # ~7 hours at 5-min cadence
            interval_minutes=5,
            speed_knots=9.0,
            rng=rng,
        )
    )

    # --- Vessel D: anomalous. Passes near the origin during the window,
    # like Vessel A, but has a 90-minute AIS reporting gap and an abrupt
    # course + speed change right after the gap. ---
    d_start = window_mid - timedelta(hours=1, minutes=30)
    d_approach = (
        center_lat - _km_to_deg_lat(15),
        center_lon + _km_to_deg_lon(18, center_lat),
    )
    d_depart = (
        center_lat + _km_to_deg_lat(2),
        center_lon - _km_to_deg_lon(22, center_lat),
    )
    n_points_d = 37  # 3 hours at 5-min cadence
    drop = set(range(14, 32))  # ~90 minute gap in the middle of the track
    d_df = _straight_track(
        mmsi="419000004",
        vessel_name="MV SILVER TIDE",
        start_latlon=d_approach,
        end_latlon=d_depart,
        start_time=d_start,
        n_points=n_points_d,
        interval_minutes=5,
        speed_knots=8.0,
        rng=rng,
        drop_indices=drop,
    )
    # Inject an abrupt speed/course change on the first point after the gap
    if len(d_df) > 15:
        d_df.loc[d_df.index[15], "sog"] = 21.0
        d_df.loc[d_df.index[15], "cog"] = (d_df.loc[d_df.index[15], "cog"] + 140) % 360
        d_df.loc[d_df.index[15], "heading"] = d_df.loc[d_df.index[15], "cog"]
    tracks.append(d_df)

    # --- Background vessels: ordinary traffic in the wider region,
    # present at various times, should all rank below A. ---
    bg_specs = [
        (
            "419000010",
            "MV HARBOUR LINK",
            (center_lat + _km_to_deg_lat(55), center_lon + _km_to_deg_lon(10, center_lat)),
            (center_lat + _km_to_deg_lat(50), center_lon + _km_to_deg_lon(25, center_lat)),
            window_start - timedelta(hours=1),
            9.5,
        ),
        (
            "419000011",
            "MV DELTA VOYAGER",
            (center_lat - _km_to_deg_lat(60), center_lon - _km_to_deg_lon(5, center_lat)),
            (center_lat - _km_to_deg_lat(45), center_lon + _km_to_deg_lon(8, center_lat)),
            window_start + timedelta(hours=2),
            12.0,
        ),
        (
            "419000012",
            "MV OCEAN PIONEER",
            (center_lat + _km_to_deg_lat(8), center_lon + _km_to_deg_lon(50, center_lat)),
            (center_lat - _km_to_deg_lat(5), center_lon + _km_to_deg_lon(60, center_lat)),
            window_start + timedelta(hours=1),
            13.5,
        ),
    ]
    for mmsi, name, p1, p2, t0, speed in bg_specs:
        tracks.append(
            _straight_track(
                mmsi=mmsi,
                vessel_name=name,
                start_latlon=p1,
                end_latlon=p2,
                start_time=t0,
                n_points=30,
                interval_minutes=6,
                speed_knots=speed,
                rng=rng,
            )
        )

    full = pd.concat(tracks, ignore_index=True)
    full["timestamp"] = pd.to_datetime(full["timestamp"], utc=True)
    full = full.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)
    return full


def save_synthetic_ais(module4_path: str, out_path: str, seed: int = 42) -> str:
    with open(module4_path, "r", encoding="utf-8") as f:
        module4_output = json.load(f)
    df = generate_synthetic_ais(module4_output, seed=seed)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return out_path


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SYNTHETIC AIS data for Module 5 development/demo."
    )
    parser.add_argument(
        "--module4-input",
        default="data/sample/mock_module4_output.json",
        help="Path to the Module 4 origin/time-window JSON.",
    )
    parser.add_argument(
        "--out",
        default="data/sample/synthetic_ais.csv",
        help="Where to write the generated CSV.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    path = save_synthetic_ais(args.module4_input, args.out, seed=args.seed)
    print(f"Synthetic AIS data written to: {path}")


if __name__ == "__main__":
    _cli()
