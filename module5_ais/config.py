"""
config.py
---------
Central place for every tunable threshold / weight used across Module 5.

Nothing in processing.py, scoring.py or ranking.py should contain a bare
magic number for a threshold — they should all import it from here. This
makes it possible to re-tune the pipeline (or swap in real AIS data with
different noise characteristics) without touching the logic files.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module5Config:
    # --- Temporal filtering ---
    # Module 4's estimated origin time window is an estimate, not a hard
    # boundary. We widen it on both sides before filtering AIS records so
    # we don't discard a real candidate just because the drift model's
    # timing was slightly off. 2 hours is a reasonable starting buffer for
    # a coastal oil-spill scenario; tune this once Module 4 reports typical
    # uncertainty in its time-window estimate.
    time_buffer_hours: float = 2.0

    # --- Spatial filtering / distance scoring ---
    # Vessels are kept in the candidate pool if their closest approach to
    # the origin center is within radius_km * spatial_filter_factor. This
    # is deliberately looser than the origin radius itself so we don't
    # prematurely exclude vessels whose real distance score should still be
    # partially credited (e.g. Vessel C in the demo data must be *kept* in
    # the candidate pool but *scored low*, not silently dropped).
    spatial_filter_factor: float = 3.0

    # Distance score decays linearly to 0 at radius_km * distance_decay_factor.
    # A vessel exactly at the origin center scores 1.0; a vessel at the
    # edge of the origin radius scores 1 - 1/distance_decay_factor.
    distance_decay_factor: float = 3.0

    # --- Candidate extraction ---
    # A vessel needs at least this many AIS points inside the filtered
    # window to be considered a "trajectory" at all (a single ping isn't
    # enough to judge direction, speed or continuity).
    min_trajectory_points: int = 3

    # --- AIS continuity scoring ---
    # Gaps shorter than this (minutes) are treated as normal AIS reporting
    # behaviour (typical AIS class A reporting interval is 2-10 seconds to
    # a few minutes depending on speed; class B and busy channels can be
    # sparser, so we use a generous "normal" threshold for a hackathon
    # demo rather than the strict spec interval).
    gap_normal_minutes: float = 30.0
    # Gaps at or beyond this many minutes are scored as maximally
    # suspicious (continuity component floors at 0 here). This does NOT
    # mean "proof of deliberate AIS shutoff" — just the lowest continuity
    # score we assign.
    gap_severe_minutes: float = 180.0

    # --- Behavioural anomaly detection (reported separately, see scoring.py) ---
    # Speed jump (knots) between consecutive pings considered anomalous.
    anomaly_speed_jump_knots: float = 15.0
    # Course/heading jump (degrees) between consecutive pings considered
    # anomalous.
    anomaly_course_jump_degrees: float = 90.0
    # Whether to additionally run an Isolation Forest over candidate
    # vessels' behavioural features. Off by default — see scoring.py and
    # the README for why this is optional rather than load-bearing.
    use_isolation_forest: bool = False

    # --- Overall score weights (fixed by the SLICKTRACE master plan) ---
    weight_distance: float = 0.40
    weight_time: float = 0.30
    weight_trajectory: float = 0.20
    weight_continuity: float = 0.10

    # --- Output ---
    # How many ranked candidates to keep in the final output files.
    top_n_candidates: int = 10


DEFAULT_CONFIG = Module5Config()
