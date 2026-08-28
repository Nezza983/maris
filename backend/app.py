"""
MARIS — Integrated Backend
---------------------------
Orchestrates the real pipeline across modules:

  Module 2 (AI detection)   -> module2_inference.detect_oil()
  Module 3 (environment)    -> vendor/module3_environment/pipeline.build_environment()
  Module 4 (drift/tracing)  -> vendor/module4_drift/simulation.run_drift_and_trace()
                                (INTERIM implementation — swap out when the real
                                 teammate-owned module lands; same function
                                 signature/contract, so it's a drop-in replacement)
  Module 5 (AIS attribution)-> vendor/module5_ais (real, unmodified team code)

Each module's own graceful-fallback behavior (Module 3's mock environment,
Module 2's mock detection) is preserved, so a missing credential or
dependency degrades a single field rather than crashing the whole demo.
"""

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(BASE_DIR, "vendor")

# Make vendored packages importable
sys.path.insert(0, VENDOR_DIR)                                   # module5_ais (proper package)
sys.path.insert(0, os.path.join(VENDOR_DIR, "module3_environment"))  # currents.py / wind.py flat imports
sys.path.insert(0, os.path.join(VENDOR_DIR, "module4_drift"))

import module2_inference  # noqa: E402

from module3_environment.pipeline import build_environment  # noqa: E402
from module4_drift.simulation import run_drift_and_trace  # noqa: E402

from module5_ais.processing import (  # noqa: E402
    parse_time_window,
    load_ais_csv,
    spatial_filter,
    temporal_filter,
    extract_candidates,
)
from module5_ais.ranking import (  # noqa: E402
    score_all_candidates,
    rank_candidates,
    build_candidates_json,
    build_tracks_geojson,
)
from module5_ais.synthetic_ais import save_synthetic_ais  # noqa: E402
from module5_ais.config import DEFAULT_CONFIG  # noqa: E402


app = Flask(__name__)
CORS(app)


@app.route("/")
def home():
    module2_inference._try_init()
    return jsonify({
        "system": "MARIS",
        "message": "Maritime Intelligence & Response System — integrated backend",
        "status": "online",
        "modules": {
            "module2_ai": "real" if module2_inference._backend_ready else f"mock ({module2_inference._init_error})",
            "module3_environment": "real (auto mock-fallback if no CMEMS/CDS creds)",
            "module4_drift": "interim physics-based implementation (pending teammate module)",
            "module5_ais": "real (synthetic AIS)",
        },
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        # ---- Inputs ----
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No SAR image uploaded"}), 400
        image = request.files["image"]
        if image.filename == "":
            return jsonify({"success": False, "error": "No image selected"}), 400

        lat = float(request.form.get("latitude", 15.35))
        lon = float(request.form.get("longitude", 73.95))
        time_str = request.form.get(
            "timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        )

        investigation_id = "MARIS-" + os.urandom(4).hex().upper()

        # ---- Save uploaded image to a temp path for Module 2 ----
        suffix = os.path.splitext(image.filename)[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            image.save(tmp.name)
            image_path = tmp.name

        # ---- Module 2: detection ----
        detection = module2_inference.detect_oil(image_path)
        os.unlink(image_path)

        if not detection["oil_detected"]:
            return jsonify({
                "success": True,
                "investigation_id": investigation_id,
                "detection": detection,
                "message": "No oil spill detected — pipeline stops here.",
            })

        # ---- Module 3: environment (auto-falls back to mock if no creds) ----
        environment = build_environment(lat, lon, time_str, use_fallback=True)

        # ---- Module 4: drift + backward source trace (interim implementation) ----
        module4_output = run_drift_and_trace(
            spill_lat=lat,
            spill_lon=lon,
            spill_time_iso=time_str,
            environment=environment,
            detection_confidence=detection["confidence"],
        )

        # ---- Module 5: AIS vessel attribution ----
        vessels_result = _run_module5(module4_output)

        response = {
            "success": True,
            "investigation_id": investigation_id,
            "status": "complete",
            "detection": {
                "oil_detected": detection["oil_detected"],
                "confidence": detection["confidence"],
                "severity": detection["severity"],
                "mode": detection["mode"],
            },
            "spill": {
                "latitude": lat,
                "longitude": lon,
                "timestamp": time_str,
            },
            "environment": {
                "wind_speed_ms": round((environment["wind_u"] ** 2 + environment["wind_v"] ** 2) ** 0.5, 2),
                "wind_u": environment["wind_u"],
                "wind_v": environment["wind_v"],
                "current_speed_ms": round((environment["current_u"] ** 2 + environment["current_v"] ** 2) ** 0.5, 2),
                "current_u": environment["current_u"],
                "current_v": environment["current_v"],
            },
            "drift": {
                "predicted_positions": module4_output["predicted_positions"],
                "trajectory": module4_output["trajectory"],
                "oil_age_hours": module4_output.get("oil_age_hours"),
                "oil_age_confidence": module4_output.get("oil_age_confidence"),
                "oil_age_note": module4_output.get("oil_age_note"),
            },
            "source": {
                "latitude": module4_output["origin_zone"]["center"][0],
                "longitude": module4_output["origin_zone"]["center"][1],
                "radius_km": module4_output["origin_zone"]["radius_km"],
                "confidence": module4_output["confidence"],
            },
            "risk": {
                "level": detection["severity"],
                "coastal_impact_probability": min(0.95, detection["confidence"]),
            },
            "vessels": vessels_result["vessels"],
            "vessel_tracks": vessels_result["tracks_geojson"],
        }
        return jsonify(response)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


def _run_module5(module4_output: dict) -> dict:
    """Run the real module5_ais pipeline in-process against Module 4's output."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        module4_path = os.path.join(tmp_dir, "module4_output.json")
        with open(module4_path, "w") as f:
            json.dump(module4_output, f)

        ais_csv_path = os.path.join(tmp_dir, "synthetic_ais.csv")
        save_synthetic_ais(module4_path, ais_csv_path)

        ais_df = load_ais_csv(ais_csv_path)

        origin_zone = module4_output["origin_zone"]
        window_start, window_end = parse_time_window(module4_output)

        spatially_filtered = spatial_filter(ais_df, origin_zone, DEFAULT_CONFIG)
        temporally_filtered = temporal_filter(spatially_filtered, window_start, window_end, DEFAULT_CONFIG)
        candidates = extract_candidates(temporally_filtered, DEFAULT_CONFIG)

        if not candidates:
            return {"vessels": [], "tracks_geojson": {"type": "FeatureCollection", "features": []}}

        breakdowns = score_all_candidates(candidates, origin_zone, window_start, window_end, DEFAULT_CONFIG)
        ranked = rank_candidates(breakdowns, DEFAULT_CONFIG)

        candidates_json = build_candidates_json(ranked, origin_zone, window_start, window_end)
        tracks_geojson = build_tracks_geojson(ranked, candidates)

        return {"vessels": candidates_json["candidates"], "tracks_geojson": tracks_geojson}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
