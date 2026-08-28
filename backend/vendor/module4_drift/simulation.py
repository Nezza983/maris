"""
Module 4 — Drift & Backward Source-Tracing (INTERIM IMPLEMENTATION)
--------------------------------------------------------------------
STATUS: This file was empty on every branch of the repo at integration
time. This is a temporary, physics-based stand-in written to unblock
the end-to-end demo. It should be replaced by the real teammate-owned
OpenDrift-based module as soon as it's pushed — the function signature
and output contract below are exactly what Module 5 already expects,
so swapping it in later is a drop-in replacement (no other code needs
to change).

WHAT IT DOES
------------
Given the detected spill location/time and the wind/current vector at
that point (from Module 3), this:
  1. Combines current velocity with a wind-drift contribution (the
     standard ~3% of wind speed, ~20 deg deflection is a common rough
     approximation for surface oil drift used in operational spill
     models such as OpenDrift's OpenOil).
  2. Projects that combined drift vector FORWARD in time to produce a
     short predicted trajectory (for the map).
  3. Projects the same vector BACKWARD in time over `lookback_hours` to
     estimate a probable origin point, and wraps it in a circular
     uncertainty zone whose radius grows with lookback time (further
     back = less certain).

This is a simplified straight-line (constant-vector) advection, not a
full Lagrangian particle simulation — it does not account for wind/
current changes over time, coastline interaction, or diffusion/
spreading. It is meant to produce a *plausible, demoable* estimate,
not a scientifically validated one.

OUTPUT CONTRACT (must match what module5_ais.processing.load_module4_output expects)
-------------------------------------------------------------------------------------
{
  "origin_zone": {"type": "circle", "center": [lat, lon], "radius_km": float},
  "time_window": {"start": ISO8601 str, "end": ISO8601 str},
  "confidence": float in [0, 1],
  "predicted_positions": [{"latitude": .., "longitude": .., "time": ISO8601}, ...],
  "trajectory": [[lon, lat], ...]   # GeoJSON-style, for map polylines
}
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


EARTH_RADIUS_KM = 6371.0

# Rough operational-model constants (OpenOil-style approximation)
WIND_DRIFT_FACTOR = 0.03       # oil moves at ~3% of wind speed
WIND_DEFLECTION_DEG = 20.0     # deflected ~20 deg from wind direction (Coriolis-ish effect)


def _deg_to_rad(d):
    return d * math.pi / 180.0


def _rad_to_deg(r):
    return r * 180.0 / math.pi


def _offset_position(lat, lon, u_ms, v_ms, seconds):
    """
    Move a point (lat, lon) by velocity (u=east m/s, v=north m/s) over
    `seconds`, using an equirectangular approximation (fine at the
    short distances/timescales involved here).
    """
    dx_km = (u_ms * seconds) / 1000.0
    dy_km = (v_ms * seconds) / 1000.0

    lat_rad = _deg_to_rad(lat)
    new_lat = lat + _rad_to_deg(dy_km / EARTH_RADIUS_KM)
    new_lon = lon + _rad_to_deg(dx_km / (EARTH_RADIUS_KM * math.cos(lat_rad)))
    return new_lat, new_lon


def _rotate_vector(u, v, degrees):
    """Rotate a 2D vector (u east, v north) by `degrees` clockwise."""
    theta = _deg_to_rad(degrees)
    u2 = u * math.cos(theta) + v * math.sin(theta)
    v2 = -u * math.sin(theta) + v * math.cos(theta)
    return u2, v2


def combined_drift_vector(current_u, current_v, wind_u, wind_v):
    """
    Combine ocean current (direct advection) with wind drift (partial,
    deflected contribution) into one effective surface-drift vector.
    """
    wind_drift_u, wind_drift_v = _rotate_vector(
        wind_u * WIND_DRIFT_FACTOR, wind_v * WIND_DRIFT_FACTOR, WIND_DEFLECTION_DEG
    )
    eff_u = current_u + wind_drift_u
    eff_v = current_v + wind_drift_v
    return eff_u, eff_v


def run_drift_and_trace(
    spill_lat: float,
    spill_lon: float,
    spill_time_iso: str,
    environment: dict,
    lookback_hours: float = 6.0,
    forecast_hours: float = 3.0,
    forecast_steps: int = 3,
    detection_confidence: float = 0.9,
) -> dict:
    """
    Main entry point. `environment` is Module 3's output dict, expected
    to contain wind_u, wind_v, current_u, current_v (all m/s).
    """
    try:
        spill_time = datetime.fromisoformat(spill_time_iso.replace("Z", "+00:00"))
    except ValueError:
        spill_time = datetime.now(timezone.utc)
    if spill_time.tzinfo is None:
        spill_time = spill_time.replace(tzinfo=timezone.utc)

    eff_u, eff_v = combined_drift_vector(
        environment.get("current_u", 0.0),
        environment.get("current_v", 0.0),
        environment.get("wind_u", 0.0),
        environment.get("wind_v", 0.0),
    )

    # --- Forward projection (for map trajectory) ---
    predicted_positions = []
    trajectory = []
    step_seconds = (forecast_hours * 3600.0) / forecast_steps
    lat, lon = spill_lat, spill_lon
    for step in range(1, forecast_steps + 1):
        lat, lon = _offset_position(lat, lon, eff_u, eff_v, step_seconds)
        t = spill_time + timedelta(seconds=step_seconds * step)
        predicted_positions.append({
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        trajectory.append([round(lon, 6), round(lat, 6)])

    # --- Backward trace (for probable source) ---
    lookback_seconds = lookback_hours * 3600.0
    origin_lat, origin_lon = _offset_position(
        spill_lat, spill_lon, -eff_u, -eff_v, lookback_seconds
    )

    drift_speed_ms = math.hypot(eff_u, eff_v)
    # Uncertainty radius grows with both time and drift speed (more
    # motion = more accumulated uncertainty in a constant-vector model).
    radius_km = max(2.0, (drift_speed_ms * lookback_seconds / 1000.0) * 0.35 + 1.5)

    # Confidence decays with lookback time and with weak/noisy drift
    # signal (very small drift vector = direction is poorly determined).
    time_decay = max(0.3, 1.0 - (lookback_hours / 24.0))
    speed_penalty = 1.0 if drift_speed_ms > 0.05 else 0.6
    confidence = round(min(0.95, detection_confidence * time_decay * speed_penalty), 2)

    window_start = spill_time - timedelta(hours=lookback_hours + 2)
    window_end = spill_time - timedelta(hours=max(0.0, lookback_hours - 2))

    return {
        "origin_zone": {
            "type": "circle",
            "center": [round(origin_lat, 6), round(origin_lon, 6)],
            "radius_km": round(radius_km, 2),
        },
        "time_window": {
            "start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "confidence": confidence,
        "predicted_positions": predicted_positions,
        "trajectory": trajectory,
        "drift_vector_ms": {"u": round(eff_u, 4), "v": round(eff_v, 4)},
        "oil_age_hours": lookback_hours,
        "oil_age_method": "assumed_lookback_window",
        "oil_age_confidence": round(min(0.5, confidence), 2),  # deliberately capped — this is an assumed window, not a measured age
        "oil_age_note": "Estimated as the backward-trace lookback window, not derived from spill area growth. A validated area-growth-based estimate (Fay spreading model) is designed but not yet wired into the live pipeline.",
    }
