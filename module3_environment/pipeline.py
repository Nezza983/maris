"""
Module 3 - Environment Data Pipeline

Main entry point that fetches wind (ERA5/CDS) and ocean current (CMEMS) data
for a given spill location/time and produces environment.json for Module 4
(OpenDrift simulation).

Usage:
    python pipeline.py
    python pipeline.py --lat -18.0 --lon 147.0 --time 2022-07-15T06:00:00Z
    python pipeline.py --mock

Environment variables:
    CMEMS_USER  - Copernicus Marine email
    CMEMS_PASS  - Copernicus Marine password
    CDS_KEY     - CDS API key

Inter-module integration:
    Reads spill location from integration/spill_input.json (written by Module 1).
    Falls back to built-in demo values if the file is not found.
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path


# Defaults (used when spill_input.json is not available)
DEMO_LAT = -18.00
DEMO_LON = 147.00
DEMO_TIME = "2022-07-15T06:00:00"

# Path to the shared input file from Module 1
INTEGRATION_DIR = Path(__file__).resolve().parent.parent / "integration"
SPILL_INPUT_PATH = INTEGRATION_DIR / "spill_input.json"

OUTPUT_PATH = Path(__file__).resolve().parent / "environment.json"

# Sanity-check bounds
WIND_RANGE = (-30, 30)
CURRENT_RANGE = (-3, 3)


def get_mock_environment(lat, lon, time_str):
    """Physically plausible placeholder values so Module 4 is never blocked."""
    return {
        "time": time_str,
        "latitude": lat,
        "longitude": lon,
        "wind_u": round(random.uniform(-8, 8), 2),
        "wind_v": round(random.uniform(-8, 8), 2),
        "current_u": round(random.uniform(-0.5, 0.5), 2),
        "current_v": round(random.uniform(-0.5, 0.5), 2),
    }


def load_spill_input():
    """
    Read the latest spill location/time from Module 1 shared JSON file.
    Falls back to hardcoded demo values if unavailable.
    """
    try:
        with open(SPILL_INPUT_PATH) as f:
            data = json.load(f)
        lat = float(data["latitude"])
        lon = float(data["longitude"])
        time_str = data["timestamp"]
        print("Loaded spill input from " + SPILL_INPUT_PATH.name)
        print("  lat=" + str(lat) + ", lon=" + str(lon) + ", time=" + time_str)
        if "image_id" in data:
            print("  (source image: " + data["image_id"] + ")")
        return lat, lon, time_str
    except FileNotFoundError:
        print("[WARN] " + str(SPILL_INPUT_PATH) + " not found. Using demo fallback.")
        return DEMO_LAT, DEMO_LON, DEMO_TIME
    except (json.JSONDecodeError, KeyError) as e:
        print("[WARN] Error parsing " + str(SPILL_INPUT_PATH) + ": " + str(e))
        return DEMO_LAT, DEMO_LON, DEMO_TIME


def sanity_check(env):
    """Validate that output values are physically reasonable."""
    checks = [
        ("wind_u", WIND_RANGE[0], WIND_RANGE[1]),
        ("wind_v", WIND_RANGE[0], WIND_RANGE[1]),
        ("current_u", CURRENT_RANGE[0], CURRENT_RANGE[1]),
        ("current_v", CURRENT_RANGE[0], CURRENT_RANGE[1]),
    ]
    ok = True
    for key, lo, hi in checks:
        val = env[key]
        status = "OK" if lo <= val <= hi else "SUSPICIOUS"
        if status == "SUSPICIOUS":
            ok = False
        print("  " + key + ": " + str(val) + "  [" + status + "]")
    if ok:
        print("")
        print("All values look physically reasonable.")
    else:
        print("")
        print("WARNING: check flagged values before handing off to Module 4.")
    return ok


def build_environment(lat, lon, time_str, use_fallback=True):
    """
    Fetch real data from CMEMS + ERA5, or fall back to mock values.
    """
    cmems_user = os.environ.get("CMEMS_USER")
    cmems_pass = os.environ.get("CMEMS_PASS")
    cds_key = os.environ.get("CDS_KEY")

    try:
        # Ocean currents (CMEMS)
        from currents import get_currents

        if not cmems_user or not cmems_pass:
            raise EnvironmentError(
                "Set CMEMS_USER and CMEMS_PASS environment variables."
            )

        print("Fetching ocean currents from CMEMS...")
        current_u, current_v = get_currents(lat, lon, time_str,
                                            cmems_user, cmems_pass)
        print("  currents: u=%.4f, v=%.4f m/s" % (current_u, current_v))

        # Wind (ERA5 / CDS)
        from wind import get_wind

        if not cds_key:
            raise EnvironmentError("Set CDS_KEY environment variable.")

        print("Fetching wind from ERA5 (CDS)...")
        wind_u, wind_v = get_wind(lat, lon, time_str, cds_key)
        print("  wind:     u=%.4f, v=%.4f m/s" % (wind_u, wind_v))

        result = {
            "time": time_str,
            "latitude": lat,
            "longitude": lon,
            "wind_u": wind_u,
            "wind_v": wind_v,
            "current_u": current_u,
            "current_v": current_v,
        }

    except Exception as e:
        print("[WARN] Live fetch failed (" + str(e) + ").")
        if not use_fallback:
            raise
        print("Using mock fallback data.")
        result = get_mock_environment(lat, lon, time_str)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Module 3 - Fetch wind and current data, output environment.json"
    )
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--time", type=str, help="ISO 8601 timestamp")
    parser.add_argument("--mock", action="store_true",
                        help="Skip APIs, use mock data immediately")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Fail hard instead of falling back to mock data")
    parser.add_argument("-o", "--output", type=str, default=str(OUTPUT_PATH),
                        help="Output file path (default: environment.json)")
    args = parser.parse_args()

    # Determine lat/lon/time
    if args.lat is not None and args.lon is not None and args.time is not None:
        lat, lon, time_str = args.lat, args.lon, args.time
    else:
        lat, lon, time_str = load_spill_input()
        if args.lat is not None:
            lat = args.lat
        if args.lon is not None:
            lon = args.lon
        if args.time is not None:
            time_str = args.time

    print("")
    print("Target: lat=" + str(lat) + ", lon=" + str(lon) + ", time=" + time_str)
    print("")

    if args.mock:
        result = get_mock_environment(lat, lon, time_str)
    else:
        result = build_environment(
            lat, lon, time_str,
            use_fallback=not args.no_fallback,
        )

    # Write output
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print("")
    print("Wrote " + str(output_path) + ":")
    print(json.dumps(result, indent=2))

    # Sanity check
    print("")
    print("Sanity check:")
    sanity_check(result)


if __name__ == "__main__":
    main()
