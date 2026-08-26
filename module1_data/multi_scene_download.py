
import ee
import geemap
import json
import os
import re
import rasterio
import numpy as np

# ============================================================
# SLICKTRACE MODULE 1
# COMPLETE SENTINEL-1 SAR DATASET DOWNLOADER
# ============================================================

PROJECT_ID = "indigo-terra-471402-m8"

SELECTED_SCENES = "metadata/selected_scenes.json"

OUTPUT_DIR = "data/raw"

TILES_PER_SCENE = 3

SCALE = 10

AOI_SIZE_METERS = 2500


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
# INITIALIZE EARTH ENGINE
# ============================================================

def initialize_earth_engine():

    print("Initializing Google Earth Engine...")

    ee.Initialize(
        project=PROJECT_ID
    )

    print(
        "Earth Engine initialized successfully."
    )


# ============================================================
# GET IMAGE
# ============================================================

def get_image(image_id):

    collection = (
        ee.ImageCollection(
            "COPERNICUS/S1_GRD"
        )
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
# GET REGION
# ============================================================

def get_region(region_name):

    if region_name not in REGION_BOUNDS:

        raise ValueError(
            f"Unknown region: {region_name}"
        )

    b = REGION_BOUNDS[
        region_name
    ]

    return ee.Geometry.Rectangle(
        [
            b["min_lon"],
            b["min_lat"],
            b["max_lon"],
            b["max_lat"],
        ],
        proj="EPSG:4326",
        geodesic=False
    )


# ============================================================
# FIND INTERSECTION
# ============================================================

def get_intersection(
    image,
    region_name
):

    region = get_region(
        region_name
    )

    footprint = image.geometry()

    intersection = region.intersection(
        footprint,
        ee.ErrorMargin(1000)
    )

    return intersection


# ============================================================
# CREATE CANDIDATE AOIs
# ============================================================

def create_candidate_aois(
    image,
    region_name
):

    intersection = get_intersection(
        image,
        region_name
    )

    bounds = intersection.bounds(
        ee.ErrorMargin(1000)
    )

    coordinates = (
        bounds
        .coordinates()
        .getInfo()[0]
    )

    xs = [
        p[0]
        for p in coordinates
    ]

    ys = [
        p[1]
        for p in coordinates
    ]

    min_lon = min(xs)
    max_lon = max(xs)

    min_lat = min(ys)
    max_lat = max(ys)

    width = max_lon - min_lon
    height = max_lat - min_lat

    positions = [

        (0.20, 0.20),
        (0.50, 0.20),
        (0.80, 0.20),

        (0.20, 0.50),
        (0.50, 0.50),
        (0.80, 0.50),

        (0.20, 0.80),
        (0.50, 0.80),
        (0.80, 0.80),

    ]

    aois = []

    for px, py in positions:

        lon = (
            min_lon
            + width * px
        )

        lat = (
            min_lat
            + height * py
        )

        point = ee.Geometry.Point(
            [
                lon,
                lat
            ]
        )

        aoi = (
            point
            .buffer(
                AOI_SIZE_METERS
            )
            .bounds()
        )

        aoi = aoi.intersection(
            intersection,
            ee.ErrorMargin(100)
        )

        aois.append(
            aoi
        )

    return aois


# ============================================================
# CHECK AOI FOR VALID VV/VH PIXELS
# ============================================================

def check_aoi(
    image,
    aoi
):

    try:

        sar = image.select(
            [
                "VV",
                "VH"
            ]
        )

        samples = (
            sar
            .sample(
                region=aoi,
                scale=SCALE,
                numPixels=1000,
                geometries=False,
                dropNulls=True
            )
        )

        count = (
            samples
            .size()
            .getInfo()
        )

        return count

    except Exception as e:

        print(
            "AOI validation error:",
            e
        )

        return 0


# ============================================================
# FIND MULTIPLE VALID AOIs
# ============================================================

def find_valid_aois(
    image,
    region_name,
    required_count=3
):

    print(
        "Searching for valid VV/VH AOIs..."
    )

    candidates = create_candidate_aois(
        image,
        region_name
    )

    valid_aois = []

    for index, aoi in enumerate(
        candidates,
        start=1
    ):

        if len(valid_aois) >= required_count:

            break

        print(
            f"Testing candidate "
            f"{index}/{len(candidates)}..."
        )

        count = check_aoi(
            image,
            aoi
        )

        print(
            f"Valid VV/VH samples: {count}"
        )

        if count >= 100:

            print(
                "  -> VALID AOI"
            )

            valid_aois.append(
                aoi
            )

        else:

            print(
                "  -> insufficient valid data"
            )

    print()
    print(
        f"Valid AOIs selected: "
        f"{len(valid_aois)}"
    )

    return valid_aois


# ============================================================
# SAFE FILENAME
# ============================================================

def safe_filename(
    name
):

    return re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        name
    )


# ============================================================
# DOWNLOAD ONE TILE
# ============================================================

def download_tile(
    image,
    region_name,
    date,
    image_id,
    tile_number,
    aoi
):

    # Use image ID in filename to prevent
    # different scenes with the same date/region
    # from overwriting one another.

    short_id = (
        image_id[-8:]
        if image_id
        else "scene"
    )

    filename = (
        f"{safe_filename(region_name)}_"
        f"{date}_"
        f"{short_id}_"
        f"tile_{tile_number:03d}.tif"
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        filename
    )

    print()
    print("-" * 70)

    print(
        f"Region : {region_name}"
    )

    print(
        f"Date   : {date}"
    )

    print(
        f"Scene  : {image_id}"
    )

    print(
        f"Tile   : {tile_number}"
    )

    print(
        f"Output : {filename}"
    )

    print("-" * 70)

    # --------------------------------------------------------
    # VV + VH
    # --------------------------------------------------------

    sar = (
        image
        .select(
            [
                "VV",
                "VH"
            ]
        )
        .toFloat()
        .clip(aoi)
    )

    try:

        print(
            "Downloading VV + VH SAR data..."
        )

        geemap.ee_export_image(
            sar,
            filename=output_path,
            scale=SCALE,
            region=aoi,
            file_per_band=False,
            crs="EPSG:4326",
        )

        print(
            "Download completed."
        )

    except Exception as e:

        print()
        print(
            "DOWNLOAD ERROR:"
        )

        print(e)

        return False

    if not os.path.exists(
        output_path
    ):

        print(
            "ERROR: Output file does not exist."
        )

        return False

    return validate_tiff(
        output_path
    )


# ============================================================
# VALIDATE TIFF
# ============================================================

def validate_tiff(
    output_path
):

    print()
    print(
        "Validating downloaded GeoTIFF..."
    )

    try:

        with rasterio.open(
            output_path
        ) as src:

            print(
                f"  CRS   : {src.crs}"
            )

            print(
                f"  Width : {src.width}"
            )

            print(
                f"  Height: {src.height}"
            )

            print(
                f"  Bands : {src.count}"
            )

            if src.count != 2:

                print(
                    "  ERROR: Expected 2 bands."
                )

                return False

            total_pixels = (
                src.width
                * src.height
            )

            total_finite = 0

            for band_number in [
                1,
                2
            ]:

                data = src.read(
                    band_number
                )

                finite = np.isfinite(
                    data
                )

                finite_count = int(
                    finite.sum()
                )

                total_finite += (
                    finite_count
                )

                print()
                print(
                    f"  Band {band_number}:"
                )

                print(
                    f"    dtype  = "
                    f"{data.dtype}"
                )

                print(
                    f"    finite = "
                    f"{finite_count}/"
                    f"{total_pixels}"
                )

                if finite_count > 0:

                    values = data[
                        finite
                    ]

                    print(
                        f"    min    = "
                        f"{values.min():.4f}"
                    )

                    print(
                        f"    max    = "
                        f"{values.max():.4f}"
                    )

                    print(
                        f"    mean   = "
                        f"{values.mean():.4f}"
                    )

                    print(
                        f"    std    = "
                        f"{values.std():.4f}"
                    )

                else:

                    print(
                        "    ERROR: "
                        "No finite pixels."
                    )

            if total_finite == 0:

                print(
                    "  ERROR: "
                    "No valid SAR pixels."
                )

                return False

    except Exception as e:

        print(
            "  TIFF validation error:"
        )

        print(e)

        return False

    size_mb = (
        os.path.getsize(
            output_path
        )
        / (1024 * 1024)
    )

    print()
    print(
        f"  File size: {size_mb:.2f} MB"
    )

    print(
        "  VALID SAR GeoTIFF"
    )

    return True


# ============================================================
# PROCESS ONE SCENE
# ============================================================

def process_scene(
    scene,
    scene_number,
    total_scenes
):

    region = scene[
        "region"
    ]

    image_id = scene[
        "image_id"
    ]

    date = scene[
        "date"
    ]

    print()
    print("=" * 70)

    print(
        f"SCENE {scene_number}/{total_scenes}"
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

    # --------------------------------------------------------
    # LOAD IMAGE
    # --------------------------------------------------------

    try:

        image = get_image(
            image_id
        )

        confirmed_id = (
            image
            .get(
                "system:index"
            )
            .getInfo()
        )

        print(
            "Confirmed image:",
            confirmed_id
        )

    except Exception as e:

        print(
            "ERROR loading image:"
        )

        print(e)

        return 0, 1

    # --------------------------------------------------------
    # CHECK BANDS
    # --------------------------------------------------------

    try:

        bands = (
            image
            .bandNames()
            .getInfo()
        )

        print(
            "Available bands:",
            bands
        )

        if (
            "VV" not in bands
            or "VH" not in bands
        ):

            print(
                "ERROR: VV/VH bands unavailable."
            )

            return 0, 1

    except Exception as e:

        print(
            "ERROR checking bands:"
        )

        print(e)

        return 0, 1

    # --------------------------------------------------------
    # FIND VALID AOIs
    # --------------------------------------------------------

    valid_aois = find_valid_aois(
        image,
        region,
        required_count=TILES_PER_SCENE
    )

    if len(valid_aois) == 0:

        print(
            "ERROR: No valid AOIs found."
        )

        return 0, 1

    # --------------------------------------------------------
    # DOWNLOAD TILES
    # --------------------------------------------------------

    successful = 0
    failed = 0

    for tile_index, aoi in enumerate(
        valid_aois,
        start=1
    ):

        success = download_tile(
            image,
            region,
            date,
            image_id,
            tile_index,
            aoi
        )

        if success:

            successful += 1

        else:

            failed += 1

    return successful, failed


# ============================================================
# REMOVE OLD ZERO-BYTE / INVALID FILES
# ============================================================

def clean_invalid_files():

    if not os.path.exists(
        OUTPUT_DIR
    ):

        return

    for filename in os.listdir(
        OUTPUT_DIR
    ):

        if not filename.lower().endswith(
            ".tif"
        ):

            continue

        path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        try:

            if os.path.getsize(
                path
            ) == 0:

                os.remove(
                    path
                )

        except Exception:

            pass


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "SLICKTRACE MODULE 1"
    )

    print(
        "COMPLETE SENTINEL-1 SAR DATASET GENERATOR"
    )

    print("=" * 70)

    print()

    print(
        "Official study area:"
    )

    print(
        f"Longitude: "
        f"{OFFICIAL_BOUNDS['min_lon']} "
        f"-> "
        f"{OFFICIAL_BOUNDS['max_lon']}"
    )

    print(
        f"Latitude : "
        f"{OFFICIAL_BOUNDS['min_lat']} "
        f"-> "
        f"{OFFICIAL_BOUNDS['max_lat']}"
    )

    # --------------------------------------------------------
    # CREATE OUTPUT DIRECTORY
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    clean_invalid_files()

    # --------------------------------------------------------
    # INITIALIZE EE
    # --------------------------------------------------------

    try:

        initialize_earth_engine()

    except Exception as e:

        print()
        print(
            "Earth Engine initialization failed:"
        )

        print(e)

        return

    # --------------------------------------------------------
    # LOAD SCENES
    # --------------------------------------------------------

    if not os.path.exists(
        SELECTED_SCENES
    ):

        print()
        print(
            "ERROR: selected_scenes.json not found:"
        )

        print(
            SELECTED_SCENES
        )

        return

    try:

        with open(
            SELECTED_SCENES,
            "r"
        ) as f:

            scenes = json.load(f)

    except Exception as e:

        print(
            "ERROR reading selected_scenes.json:"
        )

        print(e)

        return

    print()
    print(
        f"Scene entries found: "
        f"{len(scenes)}"
    )

    # --------------------------------------------------------
    # REMOVE DUPLICATE IMAGE IDS
    # --------------------------------------------------------

    unique_scenes = []

    seen_ids = set()

    for scene in scenes:

        image_id = scene.get(
            "image_id"
        )

        if not image_id:

            continue

        if image_id in seen_ids:

            continue

        seen_ids.add(
            image_id
        )

        unique_scenes.append(
            scene
        )

    print(
        f"Unique scenes: "
        f"{len(unique_scenes)}"
    )

    print()
    print(
        f"Target tiles: "
        f"{len(unique_scenes) * TILES_PER_SCENE}"
    )

    # --------------------------------------------------------
    # PROCESS ALL SCENES
    # --------------------------------------------------------

    total_success = 0
    total_failed = 0

    total = len(
        unique_scenes
    )

    for scene_number, scene in enumerate(
        unique_scenes,
        start=1
    ):

        successful, failed = process_scene(
            scene,
            scene_number,
            total
        )

        total_success += successful
        total_failed += failed

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "MODULE 1 DATASET GENERATION COMPLETE"
    )

    print("=" * 70)

    print(
        f"Unique scenes processed: "
        f"{len(unique_scenes)}"
    )

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
        "Output directory:"
    )

    print(
        os.path.abspath(
            OUTPUT_DIR
        )
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
