"""
test_module5.py
----------------
Pytest suite for Module 5. Covers each pipeline stage individually with
small hand-built DataFrames (fast, deterministic, easy to reason about),
plus one full end-to-end test against the actual synthetic dataset to
confirm the intended "strong candidate" scenario ranks correctly.

Run with:  pytest module5_ais/tests -v
"""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from module5_ais.config import Module5Config
from module5_ais.processing import (
    spatial_filter,
    temporal_filter,
    extract_candidates,
    load_module4_output,
    parse_time_window,
)
from module5_ais.scoring import (
    closest_approach,
    distance_score,
    time_score,
    trajectory_score,
    continuity_score,
    compute_vessel_score,
)
from module5_ais.ranking import (
    score_all_candidates,
    rank_candidates,
    build_candidates_json,
    build_tracks_geojson,
)
from module5_ais.synthetic_ais import generate_synthetic_ais


MODULE4_PATH = "data/sample/mock_module4_output.json"
ORIGIN = {"type": "circle", "center": [14.50, 74.85], "radius_km": 15}
WINDOW_START = pd.Timestamp("2026-08-20T10:00:00Z")
WINDOW_END = pd.Timestamp("2026-08-20T18:00:00Z")
CONFIG = Module5Config()


def _make_ais_row(mmsi, name, t, lat, lon, sog=10.0, cog=90.0, heading=90.0):
    return {
        "mmsi": mmsi,
        "vessel_name": name,
        "timestamp": pd.Timestamp(t),
        "latitude": lat,
        "longitude": lon,
        "sog": sog,
        "cog": cog,
        "heading": heading,
    }


# ---------------------------------------------------------------------------
# Spatial filtering
# ---------------------------------------------------------------------------


def test_spatial_filter_keeps_close_drops_far():
    df = pd.DataFrame(
        [
            _make_ais_row("A", "Close Vessel", "2026-08-20T12:00:00Z", 14.50, 74.85),
            _make_ais_row("B", "Far Vessel", "2026-08-20T12:00:00Z", 16.50, 76.85),
        ]
    )
    filtered = spatial_filter(df, ORIGIN, CONFIG)
    assert set(filtered["mmsi"]) == {"A"}
    assert "distance_to_origin_km" in filtered.columns
    assert filtered.iloc[0]["distance_to_origin_km"] < 1.0


# ---------------------------------------------------------------------------
# Temporal filtering
# ---------------------------------------------------------------------------


def test_temporal_filter_respects_buffer():
    df = pd.DataFrame(
        [
            _make_ais_row("A", "In window", "2026-08-20T12:00:00Z", 14.5, 74.85),
            _make_ais_row("B", "In buffer only", "2026-08-20T09:00:00Z", 14.5, 74.85),
            _make_ais_row("C", "Outside even buffer", "2026-08-20T02:00:00Z", 14.5, 74.85),
        ]
    )
    filtered = temporal_filter(df, WINDOW_START, WINDOW_END, CONFIG)
    assert set(filtered["mmsi"]) == {"A", "B"}


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------


def test_extract_candidates_drops_short_tracks():
    df = pd.DataFrame(
        [
            _make_ais_row("A", "Enough points", t, 14.5, 74.85)
            for t in ["2026-08-20T12:00:00Z", "2026-08-20T12:05:00Z", "2026-08-20T12:10:00Z"]
        ]
        + [_make_ais_row("B", "Too few points", "2026-08-20T12:00:00Z", 14.5, 74.85)]
    )
    candidates = extract_candidates(df, CONFIG)
    assert "A" in candidates
    assert "B" not in candidates  # only 1 point, below min_trajectory_points


# ---------------------------------------------------------------------------
# Distance score
# ---------------------------------------------------------------------------


def test_distant_vessel_gets_low_distance_score():
    near_df = pd.DataFrame(
        [_make_ais_row("A", "Near", "2026-08-20T12:00:00Z", 14.50, 74.85)]
    )
    far_df = pd.DataFrame(
        [_make_ais_row("B", "Far", "2026-08-20T12:00:00Z", 15.20, 75.60)]
    )
    near_approach = closest_approach(near_df, tuple(ORIGIN["center"]))
    far_approach = closest_approach(far_df, tuple(ORIGIN["center"]))

    near_score = distance_score(near_approach, ORIGIN["radius_km"], CONFIG)
    far_score = distance_score(far_approach, ORIGIN["radius_km"], CONFIG)

    assert near_score > 0.9
    assert far_score < near_score
    assert 0.0 <= far_score <= 1.0


# ---------------------------------------------------------------------------
# Time-match score
# ---------------------------------------------------------------------------


def test_wrong_time_vessel_gets_low_time_score():
    in_window_df = pd.DataFrame(
        [
            _make_ais_row("A", "In window", t, 14.5, 74.85)
            for t in ["2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z", "2026-08-20T15:00:00Z"]
        ]
    )
    wrong_time_df = pd.DataFrame(
        [
            _make_ais_row("B", "Wrong time", t, 14.5, 74.85)
            for t in ["2026-08-20T04:00:00Z", "2026-08-20T05:00:00Z", "2026-08-20T06:00:00Z"]
        ]
    )
    in_window_score = time_score(in_window_df, WINDOW_START, WINDOW_END)
    wrong_time_score = time_score(wrong_time_df, WINDOW_START, WINDOW_END)

    assert in_window_score >= 0.5
    assert wrong_time_score == 0.0
    assert in_window_score > wrong_time_score


# ---------------------------------------------------------------------------
# AIS continuity / gap detection
# ---------------------------------------------------------------------------


def test_ais_gap_is_detected_and_penalized():
    normal_df = pd.DataFrame(
        [
            _make_ais_row("A", "Normal", t, 14.5, 74.85)
            for t in pd.date_range("2026-08-20T12:00:00Z", periods=6, freq="5min")
        ]
    )
    gappy_times = list(pd.date_range("2026-08-20T12:00:00Z", periods=3, freq="5min")) + list(
        pd.date_range("2026-08-20T15:30:00Z", periods=3, freq="5min")
    )
    gappy_df = pd.DataFrame(
        [_make_ais_row("B", "Gappy", t, 14.5, 74.85) for t in gappy_times]
    )

    normal_score, normal_gap, _ = continuity_score(normal_df, CONFIG)
    gappy_score, gappy_gap, _ = continuity_score(gappy_df, CONFIG)

    assert normal_score == 1.0
    assert gappy_gap > CONFIG.gap_normal_minutes
    assert gappy_score < normal_score


# ---------------------------------------------------------------------------
# Trajectory score sanity bounds
# ---------------------------------------------------------------------------


def test_trajectory_score_in_valid_range():
    df = pd.DataFrame(
        [
            _make_ais_row("A", "V", "2026-08-20T12:00:00Z", 14.30, 74.65, cog=45),
            _make_ais_row("A", "V", "2026-08-20T12:30:00Z", 14.50, 74.85, cog=45),
            _make_ais_row("A", "V", "2026-08-20T13:00:00Z", 14.70, 75.05, cog=45),
        ]
    )
    approach = closest_approach(df, tuple(ORIGIN["center"]))
    score = trajectory_score(df, tuple(ORIGIN["center"]), approach)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_ranking_orders_by_overall_score_descending():
    strong_df = pd.DataFrame(
        [
            _make_ais_row("A", "Strong", t, 14.50, 74.85, cog=45)
            for t in pd.date_range("2026-08-20T12:00:00Z", periods=6, freq="5min")
        ]
    )
    weak_df = pd.DataFrame(
        [
            _make_ais_row("B", "Weak", t, 15.20, 75.60, cog=200)
            for t in pd.date_range("2026-08-20T12:00:00Z", periods=6, freq="5min")
        ]
    )
    candidates = {"A": strong_df, "B": weak_df}
    breakdowns = score_all_candidates(candidates, ORIGIN, WINDOW_START, WINDOW_END, CONFIG)
    ranked = rank_candidates(breakdowns, CONFIG)

    assert ranked[0].mmsi == "A"
    assert ranked[0].overall_score >= ranked[1].overall_score


# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------


def test_candidates_json_and_geojson_are_well_formed():
    df = pd.DataFrame(
        [
            _make_ais_row("A", "Test Vessel", t, 14.50, 74.85, cog=45)
            for t in pd.date_range("2026-08-20T12:00:00Z", periods=6, freq="5min")
        ]
    )
    candidates = {"A": df}
    breakdowns = score_all_candidates(candidates, ORIGIN, WINDOW_START, WINDOW_END, CONFIG)
    ranked = rank_candidates(breakdowns, CONFIG)

    candidates_json = build_candidates_json(ranked, ORIGIN, WINDOW_START, WINDOW_END)
    # Must be JSON-serialisable and match the expected shape.
    serialized = json.dumps(candidates_json)
    reloaded = json.loads(serialized)
    assert "candidates" in reloaded
    c0 = reloaded["candidates"][0]
    for key in ["rank", "vessel_id", "vessel_name", "score", "score_breakdown", "closest_approach", "anomaly_info"]:
        assert key in c0
    assert set(c0["score_breakdown"].keys()) == {
        "distance",
        "time_match",
        "trajectory_match",
        "ais_continuity",
    }

    geojson = build_tracks_geojson(ranked, candidates)
    serialized_geo = json.dumps(geojson)
    reloaded_geo = json.loads(serialized_geo)
    assert reloaded_geo["type"] == "FeatureCollection"
    feature = reloaded_geo["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    # GeoJSON coordinates must be [lon, lat], and longitude here (~74.85)
    # is nowhere near a valid latitude range check mistake (~14.5) -
    # this guards against an accidental lat/lon swap.
    first_coord = feature["geometry"]["coordinates"][0]
    assert 70 < first_coord[0] < 80  # longitude
    assert 10 < first_coord[1] < 20  # latitude


# ---------------------------------------------------------------------------
# Full end-to-end test against the real synthetic scenario
# ---------------------------------------------------------------------------


def test_end_to_end_strong_candidate_ranks_first():
    module4_output = load_module4_output(MODULE4_PATH)
    origin_zone = module4_output["origin_zone"]
    window_start, window_end = parse_time_window(module4_output)

    ais_df = generate_synthetic_ais(module4_output, seed=42)

    spatially_filtered = spatial_filter(ais_df, origin_zone, CONFIG)
    temporally_filtered = temporal_filter(spatially_filtered, window_start, window_end, CONFIG)
    candidates = extract_candidates(temporally_filtered, CONFIG)

    assert "419000001" in candidates  # Vessel A (strong candidate) must survive filtering

    breakdowns = score_all_candidates(candidates, origin_zone, window_start, window_end, CONFIG)
    ranked = rank_candidates(breakdowns, CONFIG)

    assert ranked[0].mmsi == "419000001", "Vessel A (strong candidate) should rank #1"

    # Vessel D (anomalous) must have at least one anomaly flag recorded.
    d_breakdown = next(b for b in ranked if b.mmsi == "419000004")
    assert len(d_breakdown.anomaly.flags) > 0
