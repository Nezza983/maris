"""
scoring.py
----------
Turns a single vessel's filtered AIS trajectory into a score breakdown.

Design note on the overall score vs. anomaly detection
-------------------------------------------------------
The SLICKTRACE master plan fixes the correlation-score formula as:

    overall_score = 0.40*distance + 0.30*time_match
                  + 0.20*trajectory_match + 0.10*ais_continuity

We keep that formula exactly as specified. AIS "continuity" here means
strictly reporting-gap based (does the vessel's transponder keep
reporting normally?) - that is what the master plan's "AIS continuity"
term means, and it is 10% of the score by design.

Behavioural anomalies (sudden speed or course jumps) are a DIFFERENT
signal from reporting continuity, and folding them into the fixed
weighted formula would silently change what the master plan's weights
mean. Instead, behavioural anomaly detection (rule-based, with an
optional Isolation Forest layer) is computed separately and surfaced as
"anomaly_info" alongside the score - useful to a human investigator,
but not allowed to quietly move a vessel's rank in a way nobody asked
for. See compute_vessel_score() for exactly how these fit together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from module5_ais.config import Module5Config, DEFAULT_CONFIG
from module5_ais.geo_utils import angle_diff_deg, bearing_deg, haversine_km


@dataclass
class ClosestApproach:
    distance_km: float
    timestamp: pd.Timestamp
    latitude: float
    longitude: float
    is_interior: bool  # True if the closest point isn't the first/last record


@dataclass
class AnomalyInfo:
    max_gap_minutes: float
    n_gaps_over_normal: int
    max_speed_jump_knots: float
    max_course_jump_degrees: float
    flags: list[str] = field(default_factory=list)
    behavior_anomaly_score: float = 0.0  # 0 = normal, 1 = highly anomalous
    isolation_forest_score: Optional[float] = None  # None if not run


@dataclass
class VesselScoreBreakdown:
    mmsi: str
    vessel_name: str
    distance_score: float
    time_score: float
    trajectory_score: float
    continuity_score: float
    overall_score: float
    closest_approach: ClosestApproach
    anomaly: AnomalyInfo


# ---------------------------------------------------------------------------
# Closest approach
# ---------------------------------------------------------------------------


def closest_approach(vessel_df: pd.DataFrame, center: tuple[float, float]) -> ClosestApproach:
    """Find the vessel's nearest point (by great-circle distance) to the origin center."""
    center_lat, center_lon = center
    dists = [
        haversine_km(row.latitude, row.longitude, center_lat, center_lon)
        for row in vessel_df.itertuples()
    ]
    idx = int(np.argmin(dists))
    row = vessel_df.iloc[idx]
    is_interior = 0 < idx < len(vessel_df) - 1
    return ClosestApproach(
        distance_km=float(dists[idx]),
        timestamp=row.timestamp,
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        is_interior=is_interior,
    )


# ---------------------------------------------------------------------------
# Distance score
# ---------------------------------------------------------------------------


def distance_score(
    approach: ClosestApproach, radius_km: float, config: Module5Config = DEFAULT_CONFIG
) -> float:
    """
    Normalised distance score in [0, 1].

    What is measured: the vessel's single closest approach (great-circle
    distance) to the origin zone's center point, across all its filtered
    AIS records.

    Normalisation: score = 1.0 at distance 0 (vessel passed exactly
    through the origin center), decaying LINEARLY to 0.0 at
    radius_km * config.distance_decay_factor. A vessel exactly on the
    origin radius boundary therefore scores 1 - 1/distance_decay_factor
    (with the default factor of 3, that's about 0.67) - still a
    meaningful distance score, since "on the edge of the estimated spill
    radius" is still a real candidate, not a discarded one.

    Score of 1.0 means "passed through the estimated origin point".
    Score of 0.0 means "at or beyond the decay cutoff distance" - the
    vessel is treated as spatially irrelevant.
    """
    decay_km = radius_km * config.distance_decay_factor
    score = 1.0 - (approach.distance_km / decay_km)
    return float(np.clip(score, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Time-match score
# ---------------------------------------------------------------------------


def time_score(
    vessel_df: pd.DataFrame, window_start: pd.Timestamp, window_end: pd.Timestamp
) -> float:
    """
    Normalised time-match score in [0, 1].

    What is measured: the overlap between the vessel's own observed time
    span (its first to last AIS record in the filtered data) and Module
    4's ORIGINAL (unbuffered) estimated time window. We deliberately use
    the unbuffered window here even though temporal_filter() used a
    buffered window to decide what to include - the buffer's job is only
    to avoid prematurely discarding vessels; the score should still
    reward genuine overlap with the estimated window over "vessel merely
    caught the edge of the buffer".

    Normalisation: overlap_seconds / window_duration_seconds, clipped to
    [0, 1]. Score of 1.0 means the vessel was present for the entire
    estimated window (or longer). Score of 0.0 means no overlap with the
    unbuffered window at all (the vessel only appears in the buffer
    margin).
    """
    vessel_start = vessel_df["timestamp"].min()
    vessel_end = vessel_df["timestamp"].max()

    overlap_start = max(vessel_start, window_start)
    overlap_end = min(vessel_end, window_end)
    overlap_seconds = max(0.0, (overlap_end - overlap_start).total_seconds())

    window_seconds = (window_end - window_start).total_seconds()
    if window_seconds <= 0:
        return 0.0

    return float(np.clip(overlap_seconds / window_seconds, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Trajectory-match score
# ---------------------------------------------------------------------------


def trajectory_score(
    vessel_df: pd.DataFrame, center: tuple[float, float], approach: ClosestApproach
) -> float:
    """
    Normalised trajectory-match score in [0, 1].

    This is a deliberately transparent heuristic, not a physics-based
    trajectory model. It combines two explainable signals:

    1. Heading consistency (70% of this score): at the vessel's EARLIEST
       recorded point in the filtered data, compare the compass bearing
       from that point to the origin center against the vessel's actual
       reported course-over-ground (cog) at that time. A small angular
       difference means "the vessel was heading roughly toward the
       origin from where we first see it" - a much stronger signal than
       looking at heading at the closest-approach point itself, where by
       definition a passing vessel's bearing-to-origin is close to
       perpendicular to its course.

    2. Approach-and-departure pattern (30% of this score): whether the
       closest approach is an INTERIOR point of the trajectory (not the
       very first or last record). A vessel whose minimum distance to
       the origin occurs partway through its track actually passed by
       or through the area, rather than merely starting or ending near
       it (which could just mean the filter window clipped the track).

    Explicit limitation: this does NOT model realistic ship maneuvering,
    does not account for currents affecting a vessel's own drift, and
    does not yet incorporate speed-profile matching (e.g. slowing down
    near a discharge point). Treat it as a first-pass, explainable signal
    - a good candidate for later refinement once more AIS history and
    validated ground-truth spill cases are available.
    """
    first_row = vessel_df.iloc[0]
    bearing_to_origin = bearing_deg(
        first_row.latitude, first_row.longitude, center[0], center[1]
    )
    cog = first_row.cog
    if pd.isna(cog):
        heading_component = 0.5  # no course data available: neutral, not penalised
    else:
        diff = angle_diff_deg(bearing_to_origin, cog)
        heading_component = 1.0 - (diff / 180.0)

    pattern_component = 1.0 if approach.is_interior else 0.4

    score = 0.7 * heading_component + 0.3 * pattern_component
    return float(np.clip(score, 0.0, 1.0))


# ---------------------------------------------------------------------------
# AIS continuity score (reporting gaps only - see module docstring)
# ---------------------------------------------------------------------------


def continuity_score(
    vessel_df: pd.DataFrame, config: Module5Config = DEFAULT_CONFIG
) -> tuple[float, float, float]:
    """
    Normalised AIS continuity score in [0, 1], based purely on reporting
    gaps and interval regularity - NOT on speed/course behaviour (that is
    anomaly_score, computed separately below).

    What is measured:
      - gap_component: the single largest gap between consecutive AIS
        reports. Gaps <= config.gap_normal_minutes score 1.0 (normal AIS
        behaviour). Gaps >= config.gap_severe_minutes score 0.0. Linear
        interpolation between the two.
      - regularity_component: how consistent the reporting interval is
        overall (low variability = more "normal" AIS behaviour), based
        on the coefficient of variation of the interval series.

    continuity_score = 0.7 * gap_component + 0.3 * regularity_component

    A LOW score here is a suspicious signal (the vessel's AIS reporting
    was irregular or had a long gap during the relevant period) - it is
    NOT proof of a deliberate AIS shutdown. Equipment faults, poor
    reception, and heavy vessel traffic congestion on the AIS channel can
    all cause the same pattern.

    Returns (score, max_gap_minutes, n_gaps_over_normal) so callers can
    also report the raw numbers, not just the final score.
    """
    timestamps = vessel_df["timestamp"].sort_values().reset_index(drop=True)
    if len(timestamps) < 2:
        return 1.0, 0.0, 0

    gaps_minutes = timestamps.diff().dropna().dt.total_seconds() / 60.0
    max_gap = float(gaps_minutes.max())
    n_gaps_over_normal = int((gaps_minutes > config.gap_normal_minutes).sum())

    if max_gap <= config.gap_normal_minutes:
        gap_component = 1.0
    elif max_gap >= config.gap_severe_minutes:
        gap_component = 0.0
    else:
        span = config.gap_severe_minutes - config.gap_normal_minutes
        gap_component = 1.0 - (max_gap - config.gap_normal_minutes) / span

    mean_gap = float(gaps_minutes.mean())
    std_gap = float(gaps_minutes.std(ddof=0)) if len(gaps_minutes) > 1 else 0.0
    cv = (std_gap / mean_gap) if mean_gap > 0 else 0.0
    # A coefficient of variation of 0 (perfectly regular) -> 1.0; a cv of
    # 2.0 or more (very irregular, e.g. dominated by one big gap) -> 0.0.
    regularity_component = float(np.clip(1.0 - cv / 2.0, 0.0, 1.0))

    score = 0.7 * gap_component + 0.3 * regularity_component
    return float(np.clip(score, 0.0, 1.0)), max_gap, n_gaps_over_normal


# ---------------------------------------------------------------------------
# Behavioural anomaly detection (separate from the weighted score)
# ---------------------------------------------------------------------------


def rule_based_anomaly(
    vessel_df: pd.DataFrame,
    max_gap_minutes: float,
    n_gaps_over_normal: int,
    config: Module5Config = DEFAULT_CONFIG,
) -> AnomalyInfo:
    """
    Transparent, threshold-based anomaly detection: flags abrupt speed or
    course changes between consecutive AIS reports, plus the AIS-gap
    information already computed by continuity_score() (repeated here so
    all anomaly-relevant facts are in one place for the investigator).

    This is the DEFAULT and always-computed anomaly method. It is easy
    to explain to a judge or an investigator ("speed jumped by 13 knots
    in 5 minutes, which is above our 15-knot threshold... wait, actually
    let's check the real numbers") and does not depend on having enough
    vessels for a statistical model to be meaningful.
    """
    df = vessel_df.sort_values("timestamp").reset_index(drop=True)
    flags: list[str] = []

    speed_jumps = df["sog"].diff().abs().dropna()
    max_speed_jump = float(speed_jumps.max()) if len(speed_jumps) else 0.0

    course_series = df["cog"].dropna()
    course_jumps = course_series.diff().abs().dropna()
    # Course differences can wrap around 0/360; correct any jump > 180.
    course_jumps = course_jumps.apply(lambda d: min(d, 360 - d))
    max_course_jump = float(course_jumps.max()) if len(course_jumps) else 0.0

    n_flags = 0
    if max_speed_jump >= config.anomaly_speed_jump_knots:
        flags.append(
            f"Abrupt speed change of {max_speed_jump:.1f} knots between consecutive reports."
        )
        n_flags += 1
    if max_course_jump >= config.anomaly_course_jump_degrees:
        flags.append(
            f"Abrupt course change of {max_course_jump:.1f} degrees between consecutive reports."
        )
        n_flags += 1
    if max_gap_minutes >= config.gap_normal_minutes:
        flags.append(
            f"AIS reporting gap of {max_gap_minutes:.0f} minutes detected "
            "(equipment fault or reception loss cannot be ruled out)."
        )
        n_flags += 1

    behavior_anomaly_score = float(np.clip(n_flags / 3.0, 0.0, 1.0))

    return AnomalyInfo(
        max_gap_minutes=max_gap_minutes,
        n_gaps_over_normal=n_gaps_over_normal,
        max_speed_jump_knots=max_speed_jump,
        max_course_jump_degrees=max_course_jump,
        flags=flags,
        behavior_anomaly_score=behavior_anomaly_score,
    )


def isolation_forest_anomaly_scores(
    candidate_features: pd.DataFrame, config: Module5Config = DEFAULT_CONFIG
) -> pd.Series:
    """
    OPTIONAL Isolation Forest layer over the candidate vessels' behaviour
    features (max_speed_jump, max_course_jump, max_gap_minutes,
    interval_std). Off by default (config.use_isolation_forest = False).

    Why this is optional rather than the primary method, for a
    hackathon-scale system:
      - Isolation Forest needs a reasonably sized, reasonably
        representative sample to learn what "normal" looks like. At this
        stage of the pipeline we only have the narrowed-down CANDIDATE
        vessels (a handful, post spatial/temporal filtering) - not the
        full background AIS traffic - so with 5-15 rows its statistical
        power is weak and its output should be read as a rough,
        experimental secondary signal, not a validated probability.
      - The rule-based method above already covers the concrete
        behaviours we actually care about (speed jumps, course jumps,
        gaps) in a fully explainable way, which matters when you have to
        justify a candidate's ranking to a human investigator.

    If your team wants to strengthen this later: fit the Isolation
    Forest on a much larger background AIS sample (e.g. all vessel
    traffic in the wider region over a longer period, not just the
    filtered candidates), so it actually has enough "normal" examples to
    contrast against.

    Returns a Series of anomaly scores in [0, 1] (1 = most anomalous),
    indexed the same as candidate_features.
    """
    from sklearn.ensemble import IsolationForest

    if len(candidate_features) < 2:
        return pd.Series([0.0] * len(candidate_features), index=candidate_features.index)

    model = IsolationForest(
        n_estimators=100, contamination="auto", random_state=42
    )
    model.fit(candidate_features)
    # decision_function: higher = more normal. Flip and min-max normalise
    # to [0, 1] so 1 = most anomalous, matching behavior_anomaly_score's
    # convention.
    raw = -model.decision_function(candidate_features)
    lo, hi = raw.min(), raw.max()
    if hi - lo < 1e-9:
        return pd.Series([0.0] * len(candidate_features), index=candidate_features.index)
    normalised = (raw - lo) / (hi - lo)
    return pd.Series(normalised, index=candidate_features.index)


# ---------------------------------------------------------------------------
# Combine everything for one vessel
# ---------------------------------------------------------------------------


def compute_vessel_score(
    mmsi: str,
    vessel_df: pd.DataFrame,
    origin_zone: dict,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    config: Module5Config = DEFAULT_CONFIG,
) -> VesselScoreBreakdown:
    """
    Compute the full score breakdown for one candidate vessel.

    overall_score uses ONLY the four master-plan-specified components
    (distance, time, trajectory, continuity) at their fixed weights.
    Behavioural anomaly info is attached separately and does not affect
    overall_score - see the module docstring for why.
    """
    center = tuple(origin_zone["center"])
    radius_km = origin_zone["radius_km"]
    vessel_name = str(vessel_df["vessel_name"].iloc[0])

    approach = closest_approach(vessel_df, center)
    d_score = distance_score(approach, radius_km, config)
    t_score = time_score(vessel_df, window_start, window_end)
    traj_score = trajectory_score(vessel_df, center, approach)
    c_score, max_gap, n_gaps = continuity_score(vessel_df, config)

    overall = (
        config.weight_distance * d_score
        + config.weight_time * t_score
        + config.weight_trajectory * traj_score
        + config.weight_continuity * c_score
    )

    anomaly = rule_based_anomaly(vessel_df, max_gap, n_gaps, config)

    return VesselScoreBreakdown(
        mmsi=mmsi,
        vessel_name=vessel_name,
        distance_score=d_score,
        time_score=t_score,
        trajectory_score=traj_score,
        continuity_score=c_score,
        overall_score=float(np.clip(overall, 0.0, 1.0)),
        closest_approach=approach,
        anomaly=anomaly,
    )
