import ee
import geemap
import json
import os
import re

# ============================================================
# SLICKTRACE MODULE 1
# SENTINEL-1 VALID SAMPLE TILE DOWNLOADER
# ============================================================

PROJECT_ID = "indigo-terra-471402-m8"

SELECTED_SCENES = "metadata/selected_scenes.json"

OUTPUT_DIR = "data/raw"

# Small tile.
# Approximately 0.05 degree is roughly 5 km.
TILE_SIZE_DEGREES = 0.05

SAMPLES_PER_SCENE = 3


# ============================================================
# OFFICIAL STUDY AREA
# ============================================================

OFFICIAL_BOUNDS = {
    "min_lon": 101.41,
    "max_lon": 154.77,
    "min_lat": -26.07,
    "max_lat": 21.12,
}


# ============================================================
# REGIONAL AREAS
# ============================================================

REGION_BOUNDS = {

    "northwest_australia": {
        "min_lon": 101.41,
        "max_lon": 120.0,
        "min_lat": -20.0,
        "max_lat": -10.0,
    },

    "western_australia": {
        "min_lon": 110.0,
        "max_lon": 125.0,
        "min_lat": -26.07,
        "max_lat": -10.0,
    },

    "northern_australia": {
        "min_lon": 120.0,
        "max_lon": 145.0,
        "min_lat": -21.12,
        "max_lat": -5.0,
    },

    "great_barrier_reef": {
        "min_lon": 145.0,
        "max_lon": 154.77,
        "min_lat": -25.0,
        "max_lat": -10.0,
    },

    "eastern_australia": {
        "min_lon": 145.0,
        "max_lon": 154.77,
        "min_lat": -26.07,
        "max_lat": -21.12,
    },
}


# ============================================================
# EARTH ENGINE INITIALIZATION
# ============================================================

def initialize_earth_engine():

    print("Initializing Google Earth Engine...")

    ee.Initialize(project=PROJECT_ID)

    print("Earth Engine initialized successfully.")


# ============================================================
# GET REGION
# ============================================================

def get_region_geometry(region_name):

    if region_name not in REGION_BOUNDS:
        raise ValueError(
            f"Unknown region: {region_name}"
        )

    b = REGION_BOUNDS[region_name]

    return ee.Geometry.Rectangle([
        b["min_lon"],
        b["min_lat"],
        b["max_lon"],
        b["max_lat"],
    ])


# ============================================================
# LOAD SENTINEL-1 IMAGE
# ============================================================

def get_image(image_id):

    collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filter(
            ee.Filter.eq(
                "system:index",
                image_id
            )
        )
    )

    image = collection.first()

    return image


# ============================================================
# SAFE FILENAME
# ============================================================

def safe_filename(name):

    return re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        name
    )


# ============================================================
# FIND VALID SAMPLE POINTS
# ============================================================

def find_valid_sample_points(
    image,
    region_name
):

    region = get_region_geometry(
        region_name
    )

    # Actual Sentinel-1 footprint
    footprint = image.geometry()

    # Only use area where:
    # 1. It belongs to our study region
    # 2. It belongs to the actual Sentinel-1 scene

    valid_area = region.intersection(
        footprint,
        maxError=100
    )

    print(
        "Finding valid points inside "
        "Sentinel-1 footprint..."
    )

    # Generate random points.
    # Seed keeps the result reproducible.

    points = ee.FeatureCollection.randomPoints(
        region=valid_area,
        points=50,
        seed=42,
        maxError=100
    )

    # Add VV/VH values at each point.

    sampled = image.select(
        ["VV", "VH"]
    ).sampleRegions(
        collection=points,
        scale=10,
        geometries=True
    )

    # Keep only points where both
    # VV and VH actually exist.

    valid = sampled.filter(
        ee.Filter.notNull(
            ["VV", "VH"]
        )
    )

    features = valid.limit(
        SAMPLES_PER_SCENE
    ).getInfo()["features"]

    return features


# ============================================================
# CREATE TILE AROUND POINT
# ============================================================

def create_tile_from_point(
    feature,
    tile_id
):

    geometry = feature["geometry"]

    lon, lat = geometry["coordinates"]

    half = TILE_SIZE_DEGREES / 2

    min_lon = lon - half
    max_lon = lon + half

    min_lat = lat - half
    max_lat = lat + half

    return {
        "tile_id": tile_id,
        "lon": lon,
        "lat": lat,
        "min_lon": min_lon,
        "max_lon": max_lon,
        "min_lat": min_lat,
        "max_lat": max_lat,
    }


# ============================================================
# DOWNLOAD TILE
# ============================================================

def download_tile(
    image,
    region_name,
    date,
    tile
):

    tile_id = tile["tile_id"]

    filename = (
        f"{safe_filename(region_name)}_"
        f"{date}_"
        f"tile_{tile_id:03d}.tif"
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        filename
    )

    if os.path.exists(output_path):

        print(
            f"Already exists: {filename}"
        )

        return True

    print()
    print("-" * 70)

    print(
        f"Region : {region_name}"
    )

    print(
        f"Date   : {date}"
    )

    print(
        f"Tile   : {tile_id}"
    )

    print(
        f"Center : "
        f"{tile['lon']:.5f}, "
        f"{tile['lat']:.5f}"
    )

    print(
        f"Bounds : "
        f"{tile['min_lon']:.5f}, "
        f"{tile['min_lat']:.5f} -> "
        f"{tile['max_lon']:.5f}, "
        f"{tile['max_lat']:.5f}"
    )

    print(
        f"Output : {filename}"
    )

    print("-" * 70)

    aoi = ee.Geometry.Rectangle([
        tile["min_lon"],
        tile["min_lat"],
        tile["max_lon"],
        tile["max_lat"],
    ])

    clipped = (
        image
        .select(["VV", "VH"])
        .clip(aoi)
    )

    try:

        geemap.ee_export_image(
            clipped,
            filename=output_path,
            scale=10,
            region=aoi,
            file_per_band=False,
        )

        if not os.path.exists(output_path):

            print(
                "FAILED: File was not created."
            )

            return False

        # Validate immediately.

        import rasterio
        import numpy as np

        with rasterio.open(
            output_path
        ) as src:

            vv = src.read(1)
            vh = src.read(2)

        vv_valid = vv[
            np.isfinite(vv)
        ]

        vh_valid = vh[
            np.isfinite(vh)
        ]

        if (
            len(vv_valid) == 0
            or len(vh_valid) == 0
        ):

            print(
                "FAILED: No valid SAR pixels."
            )

            os.remove(output_path)

            return False

        vv_min = float(vv_valid.min())
        vv_max = float(vv_valid.max())

        vh_min = float(vh_valid.min())
        vh_max = float(vh_valid.max())

        # Sentinel-1 dB values should not
        # be completely zero.

        if (
            vv_min == 0
            and vv_max == 0
            and vh_min == 0
            and vh_max == 0
        ):

            print(
                "FAILED: Tile contains only zeros."
            )

            os.remove(output_path)

            return False

        size_mb = (
            os.path.getsize(output_path)
            / (1024 * 1024)
        )

        print(
            f"SUCCESS: {size_mb:.2f} MB"
        )

        print(
            f"VV range: "
            f"{vv_min:.2f} -> {vv_max:.2f}"
        )

        print(
            f"VH range: "
            f"{vh_min:.2f} -> {vh_max:.2f}"
        )

        return True

    except Exception as e:

        print("FAILED:")

        print(e)

        if os.path.exists(output_path):

            os.remove(output_path)

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "SLICKTRACE MODULE 1"
    )

    print(
        "VALID SENTINEL-1 SAMPLE DOWNLOADER"
    )

    print("=" * 70)

    print()

    print(
        "Official study area:"
    )

    print(
        f"Longitude: "
        f"{OFFICIAL_BOUNDS['min_lon']} -> "
        f"{OFFICIAL_BOUNDS['max_lon']}"
    )

    print(
        f"Latitude : "
        f"{OFFICIAL_BOUNDS['min_lat']} -> "
        f"{OFFICIAL_BOUNDS['max_lat']}"
    )

    initialize_earth_engine()

    # --------------------------------------------------------
    # Load selected scenes
    # --------------------------------------------------------

    if not os.path.exists(
        SELECTED_SCENES
    ):

        raise FileNotFoundError(
            SELECTED_SCENES
        )

    with open(
        SELECTED_SCENES,
        "r"
    ) as f:

        scenes = json.load(f)

    print()

    print(
        f"Scene entries found: "
        f"{len(scenes)}"
    )

    # --------------------------------------------------------
    # Remove duplicate scenes
    # --------------------------------------------------------

    unique_scenes = {}

    for scene in scenes:

        image_id = scene["image_id"]

        if image_id not in unique_scenes:

            unique_scenes[image_id] = scene

    scenes = list(
        unique_scenes.values()
    )

    print(
        f"Unique scenes: "
        f"{len(scenes)}"
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    total_success = 0
    total_failed = 0

    # --------------------------------------------------------
    # Process scenes
    # --------------------------------------------------------

    for scene_number, scene in enumerate(
        scenes,
        start=1
    ):

        region = scene["region"]

        image_id = scene["image_id"]

        date = scene["date"]

        print()
        print("=" * 70)

        print(
            f"SCENE {scene_number}/"
            f"{len(scenes)}"
        )

        print("=" * 70)

        print(
            f"Region: {region}"
        )

        print(
            f"Date: {date}"
        )

        print(
            f"Image: {image_id}"
        )

        # ----------------------------------------------------
        # Load image
        # ----------------------------------------------------

        try:

            image = get_image(
                image_id
            )

            confirmed_id = (
                image
                .get("system:index")
                .getInfo()
            )

            print(
                "Confirmed image:",
                confirmed_id
            )

        except Exception as e:

            print(
                "Could not load image:"
            )

            print(e)

            continue

        # ----------------------------------------------------
        # Find valid points
        # ----------------------------------------------------

        try:

            features = find_valid_sample_points(
                image,
                region
            )

            print(
                f"Valid sample points: "
                f"{len(features)}"
            )

        except Exception as e:

            print(
                "Could not find valid "
                "sample points:"
            )

            print(e)

            continue

        if len(features) == 0:

            print(
                "WARNING: No valid points "
                "found for this scene."
            )

            continue

        # ----------------------------------------------------
        # Create and download tiles
        # ----------------------------------------------------

        for index, feature in enumerate(
            features,
            start=1
        ):

            tile = create_tile_from_point(
                feature,
                index
            )

            success = download_tile(
                image,
                region,
                date,
                tile
            )

            if success:

                total_success += 1

            else:

                total_failed += 1

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "DOWNLOAD COMPLETE"
    )

    print("=" * 70)

    print(
        f"Successful tiles: "
        f"{total_success}"
    )

    print(
        f"Failed tiles: "
        f"{total_failed}"
    )

    print()

    print(
        "Raw directory:"
    )

    print(
        os.path.abspath(
            OUTPUT_DIR
        )
    )

    print("=" * 70)


if __name__ == "__main__":

    main()