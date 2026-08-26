import ee
import json
import os

PROJECT_ID = "indigo-terra-471402-m8"

ee.Initialize(project=PROJECT_ID)


# ============================================================
# OFFICIAL SLICKTRACE STUDY AREA
# ============================================================

AOIS = {

    "northwest_australia": {
        "lon_min": 115,
        "lon_max": 120,
        "lat_min": -20,
        "lat_max": -15,
        "num_scenes": 3,
    },

    "western_australia": {
        "lon_min": 120,
        "lon_max": 125,
        "lat_min": -25,
        "lat_max": -20,
        "num_scenes": 3,
    },

    "northern_australia": {
        "lon_min": 130,
        "lon_max": 135,
        "lat_min": -15,
        "lat_max": -10,
        "num_scenes": 3,
    },

    "great_barrier_reef": {
        "lon_min": 145,
        "lon_max": 153,
        "lat_min": -20,
        "lat_max": -10,
        "num_scenes": 3,
    },

    "eastern_australia": {
        "lon_min": 150,
        "lon_max": 154,
        "lat_min": -30,
        "lat_max": -20,
        "num_scenes": 3,
    },
}


START_DATE = "2026-01-01"
END_DATE = "2026-08-26"


# ============================================================
# CREATE AOI
# ============================================================

def create_aoi(config):

    return ee.Geometry.Rectangle([
        config["lon_min"],
        config["lat_min"],
        config["lon_max"],
        config["lat_max"],
    ])


# ============================================================
# SENTINEL-1 COLLECTION
# ============================================================

def get_collection(aoi):

    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")

        .filterBounds(aoi)

        .filterDate(
            START_DATE,
            END_DATE
        )

        .filter(
            ee.Filter.eq(
                "instrumentMode",
                "IW"
            )
        )

        .filter(
            ee.Filter.listContains(
                "transmitterReceiverPolarisation",
                "VV"
            )
        )

        .filter(
            ee.Filter.listContains(
                "transmitterReceiverPolarisation",
                "VH"
            )
        )

        .sort("system:time_start")
    )


# ============================================================
# GET SCENE METADATA
# ============================================================

def get_scene_info(image, region_name):

    return {
        "region": region_name,

        "image_id": image.get(
            "system:index"
        ).getInfo(),

        "date": ee.Date(
            image.get("system:time_start")
        ).format("YYYY-MM-dd").getInfo(),

        "platform": image.get(
            "platform_number"
        ).getInfo(),

        "orbit_direction": image.get(
            "orbitProperties_pass"
        ).getInfo(),

        "instrument_mode": image.get(
            "instrumentMode"
        ).getInfo(),

        "polarizations": image.get(
            "transmitterReceiverPolarisation"
        ).getInfo(),
    }


# ============================================================
# SELECT SCENES ACROSS TIME
# ============================================================

def select_spread_scenes(collection, num_scenes):

    total = collection.size().getInfo()

    if total == 0:
        return []

    if total <= num_scenes:
        positions = list(range(total))

    else:
        # Evenly distribute selections through the collection
        positions = []

        for i in range(num_scenes):

            position = round(
                i * (total - 1) / (num_scenes - 1)
            )

            positions.append(position)

    scene_list = collection.toList(total)

    selected = []

    used_ids = set()

    for position in positions:

        image = ee.Image(
            scene_list.get(position)
        )

        image_id = image.get(
            "system:index"
        ).getInfo()

        # Avoid accidental duplicate scenes
        if image_id in used_ids:
            continue

        used_ids.add(image_id)

        selected.append(image)

    return selected


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("SLICKTRACE MULTI-SCENE SELECTION")
    print("=" * 70)

    selected_scenes = []

    for region_name, config in AOIS.items():

        print()
        print("-" * 70)
        print(f"Region: {region_name}")
        print("-" * 70)

        aoi = create_aoi(config)

        collection = get_collection(aoi)

        total = collection.size().getInfo()

        print(
            f"Available scenes: {total}"
        )

        selected = select_spread_scenes(
            collection,
            config["num_scenes"]
        )

        for i, image in enumerate(
            selected,
            start=1
        ):

            info = get_scene_info(
                image,
                region_name
            )

            selected_scenes.append(info)

            print(
                f"{i}. "
                f"{info['date']} | "
                f"{info['platform']} | "
                f"{info['orbit_direction']}"
            )

            print(
                f"   {info['image_id']}"
            )


    # ========================================================
    # SAVE MANIFEST
    # ========================================================

    os.makedirs(
        "metadata",
        exist_ok=True
    )

    output_file = (
        "metadata/selected_scenes.json"
    )

    with open(
        output_file,
        "w"
    ) as f:

        json.dump(
            selected_scenes,
            f,
            indent=2
        )


    print()
    print("=" * 70)
    print(
        f"TOTAL SELECTED SCENES: "
        f"{len(selected_scenes)}"
    )

    print(
        f"Saved to: {output_file}"
    )

    print("=" * 70)