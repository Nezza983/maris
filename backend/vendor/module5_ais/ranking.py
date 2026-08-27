"""
ranking.py
----------
Combines per-vessel score breakdowns into a ranked candidate list, and
writes the two files Module 6 (frontend/dashboard) consumes:

  - vessel_candidates.json : ranked list + full score breakdown, for the
    candidate table / info panel.
  - vessel_tracks.geojson  : one LineString per candidate vessel, for
    plotting tracks on the Leaflet/Mapbox map.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from module5_ais.config import Module5Config, DEFAULT_CONFIG
from module5_ais.scoring import VesselScoreBreakdown, compute_vessel_score, isolation_forest_anomaly_scores


def score_all_candidates(
    candidates: Dict[str, pd.DataFrame],
    origin_zone: dict,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    config: Module5Config = DEFAULT_CONFIG,
) -> List[VesselScoreBreakdown]:
    """Score every candidate vessel and optionally blend in an Isolation Forest anomaly layer."""
    breakdowns = [
        compute_vessel_score(mmsi, df, origin_zone, window_start, window_end, config)
        for mmsi, df in candidates.items()
    ]

    if config.use_isolation_forest and len(breakdowns) >= 2:
        feature_rows = []
        for b in breakdowns:
            feature_rows.append(
                {
                    "max_speed_jump_knots": b.anomaly.max_speed_jump_knots,
                    "max_course_jump_degrees": b.anomaly.max_course_jump_degrees,
                    "max_gap_minutes": b.anomaly.max_gap_minutes,
                }
            )
        feature_df = pd.DataFrame(feature_rows)
        if_scores = isolation_forest_anomaly_scores(feature_df, config)
        for b, score in zip(breakdowns, if_scores):
            b.anomaly.isolation_forest_score = float(score)
            # Blend (average) with the rule-based behaviour score for the
            # reported anomaly figure. This still never touches
            # overall_score - see scoring.py's module docstring.
            b.anomaly.behavior_anomaly_score = float(
                (b.anomaly.behavior_anomaly_score + score) / 2.0
            )

    return breakdowns


def rank_candidates(
    breakdowns: List[VesselScoreBreakdown], config: Module5Config = DEFAULT_CONFIG
) -> List[VesselScoreBreakdown]:
    """Sort candidates by overall_score descending and keep the top N."""
    ranked = sorted(breakdowns, key=lambda b: b.overall_score, reverse=True)
    return ranked[: config.top_n_candidates]


def build_candidates_json(
    ranked: List[VesselScoreBreakdown],
    origin_zone: dict,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> dict:
    """
    Build the vessel_candidates.json structure. Every score in this file
    is explicitly a CORRELATION / INVESTIGATION SCORE - it ranks
    space-time-behaviour plausibility, it is NOT a probability that a
    vessel caused the spill and NOT proof of responsibility.
    """
    candidates = []
    for rank, b in enumerate(ranked, start=1):
        candidates.append(
            {
                "rank": rank,
                "vessel_id": b.mmsi,
                "vessel_name": b.vessel_name,
                "score": round(b.overall_score, 4),
                "score_label": "Correlation / Investigation Score (not proof of responsibility)",
                "score_breakdown": {
                    "distance": round(b.distance_score, 4),
                    "time_match": round(b.time_score, 4),
                    "trajectory_match": round(b.trajectory_score, 4),
                    "ais_continuity": round(b.continuity_score, 4),
                },
                "closest_approach": {
                    "distance_km": round(b.closest_approach.distance_km, 3),
                    "timestamp": b.closest_approach.timestamp.isoformat(),
                    "latitude": round(b.closest_approach.latitude, 6),
                    "longitude": round(b.closest_approach.longitude, 6),
                },
                "anomaly_info": {
                    "behavior_anomaly_score": round(b.anomaly.behavior_anomaly_score, 4),
                    "max_ais_gap_minutes": round(b.anomaly.max_gap_minutes, 1),
                    "max_speed_jump_knots": round(b.anomaly.max_speed_jump_knots, 1),
                    "max_course_jump_degrees": round(b.anomaly.max_course_jump_degrees, 1),
                    "isolation_forest_score": (
                        round(b.anomaly.isolation_forest_score, 4)
                        if b.anomaly.isolation_forest_score is not None
                        else None
                    ),
                    "flags": b.anomaly.flags,
                    "note": (
                        "Anomaly signals are informational for investigators. "
                        "They do NOT change the overall correlation score, "
                        "which follows the fixed 40/30/20/10 weighting."
                    ),
                },
            }
        )

    return {
        "generated_for": {
            "origin_zone": origin_zone,
            "time_window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
        },
        "candidates": candidates,
    }


def build_tracks_geojson(
    ranked: List[VesselScoreBreakdown], candidates: Dict[str, pd.DataFrame]
) -> dict:
    """
    Build a GeoJSON FeatureCollection with one LineString feature per
    ranked candidate vessel's track. GeoJSON coordinates are
    [longitude, latitude] - NOT [latitude, longitude] - this is handled
    correctly below.
    """
    features = []
    for rank, b in enumerate(ranked, start=1):
        df = candidates[b.mmsi].sort_values("timestamp")
        coordinates = [
            [round(float(lon), 6), round(float(lat), 6)]
            for lat, lon in zip(df["latitude"], df["longitude"])
        ]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "rank": rank,
                    "mmsi": b.mmsi,
                    "vessel_name": b.vessel_name,
                    "score": round(b.overall_score, 4),
                    "start_time": df["timestamp"].min().isoformat(),
                    "end_time": df["timestamp"].max().isoformat(),
                    "closest_approach_km": round(b.closest_approach.distance_km, 3),
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def write_outputs(
    ranked: List[VesselScoreBreakdown],
    candidates: Dict[str, pd.DataFrame],
    origin_zone: dict,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    out_dir: str,
) -> tuple[str, str]:
    """Write vessel_candidates.json and vessel_tracks.geojson to out_dir. Returns their paths."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    candidates_json = build_candidates_json(ranked, origin_zone, window_start, window_end)
    tracks_geojson = build_tracks_geojson(ranked, candidates)

    candidates_path = out_path / "vessel_candidates.json"
    tracks_path = out_path / "vessel_tracks.geojson"

    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(candidates_json, f, indent=2)
    with open(tracks_path, "w", encoding="utf-8") as f:
        json.dump(tracks_geojson, f, indent=2)

    return str(candidates_path), str(tracks_path)
