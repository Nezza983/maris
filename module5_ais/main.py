"""
main.py
-------
Module 5 end-to-end pipeline entry point.

    python -m module5_ais.main

Runs: load Module 4 output -> load/generate AIS -> validate -> spatial
filter -> temporal filter -> extract candidates -> score -> rank ->
write vessel_candidates.json + vessel_tracks.geojson -> print summary.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from module5_ais.config import DEFAULT_CONFIG
from module5_ais.processing import (
    load_module4_output,
    parse_time_window,
    load_ais_csv,
    spatial_filter,
    temporal_filter,
    extract_candidates,
)
from module5_ais.ranking import score_all_candidates, rank_candidates, write_outputs
from module5_ais.synthetic_ais import save_synthetic_ais


def run_pipeline(
    module4_path: str,
    ais_csv_path: str,
    out_dir: str,
    generate_synthetic: bool,
    config=DEFAULT_CONFIG,
) -> None:
    print("=" * 70)
    print("SLICKTRACE - Module 5: Vessel Attribution / AIS Correlation")
    print("=" * 70)

    module4_output = load_module4_output(module4_path)
    origin_zone = module4_output["origin_zone"]
    window_start, window_end = parse_time_window(module4_output)
    print(
        f"[1/8] Module 4 input loaded: origin center={origin_zone['center']}, "
        f"radius={origin_zone['radius_km']} km, "
        f"window={window_start.isoformat()} -> {window_end.isoformat()} "
        f"(confidence={module4_output.get('confidence')})"
    )

    if generate_synthetic or not os.path.exists(ais_csv_path):
        print(f"[2/8] Generating SYNTHETIC AIS data -> {ais_csv_path}")
        save_synthetic_ais(module4_path, ais_csv_path)
    else:
        print(f"[2/8] Using existing AIS file: {ais_csv_path}")

    ais_df = load_ais_csv(ais_csv_path)
    print(f"[3/8] Loaded {len(ais_df)} AIS records for {ais_df['mmsi'].nunique()} vessels.")

    spatially_filtered = spatial_filter(ais_df, origin_zone, config)
    print(
        f"[4/8] Spatial filter (<= {origin_zone['radius_km'] * config.spatial_filter_factor:.1f} km "
        f"from origin): {len(spatially_filtered)} records, "
        f"{spatially_filtered['mmsi'].nunique()} vessels remain."
    )

    temporally_filtered = temporal_filter(
        spatially_filtered, window_start, window_end, config
    )
    print(
        f"[5/8] Temporal filter (window +/- {config.time_buffer_hours}h buffer): "
        f"{len(temporally_filtered)} records, "
        f"{temporally_filtered['mmsi'].nunique()} vessels remain."
    )

    candidates = extract_candidates(temporally_filtered, config)
    print(
        f"[6/8] Candidate extraction (>= {config.min_trajectory_points} points/vessel): "
        f"{len(candidates)} candidate vessels."
    )
    if not candidates:
        print("No candidate vessels found - nothing to score. Exiting.")
        return

    breakdowns = score_all_candidates(candidates, origin_zone, window_start, window_end, config)
    ranked = rank_candidates(breakdowns, config)
    print(f"[7/8] Scored and ranked {len(ranked)} candidate(s).")

    candidates_path, tracks_path = write_outputs(
        ranked, candidates, origin_zone, window_start, window_end, out_dir
    )
    print(f"[8/8] Outputs written:\n  - {candidates_path}\n  - {tracks_path}")

    print("\n" + "-" * 70)
    print(f"{'Rank':<5}{'MMSI':<14}{'Vessel Name':<22}{'Score':<8}{'Flags'}")
    print("-" * 70)
    for rank, b in enumerate(ranked, start=1):
        flag_summary = f"{len(b.anomaly.flags)} flag(s)" if b.anomaly.flags else "-"
        print(
            f"{rank:<5}{b.mmsi:<14}{b.vessel_name:<22}{b.overall_score * 100:>5.1f}%  {flag_summary}"
        )
    print("-" * 70)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Run the Module 5 vessel attribution pipeline.")
    parser.add_argument(
        "--module4-input", default="data/sample/mock_module4_output.json"
    )
    parser.add_argument("--ais-csv", default="data/sample/synthetic_ais.csv")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Force-regenerate synthetic AIS data even if the CSV already exists.",
    )
    args = parser.parse_args()

    run_pipeline(
        module4_path=args.module4_input,
        ais_csv_path=args.ais_csv,
        out_dir=args.out_dir,
        generate_synthetic=args.generate_synthetic,
    )


if __name__ == "__main__":
    _cli()
