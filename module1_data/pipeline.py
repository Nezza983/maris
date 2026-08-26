import os

from preprocess import preprocess_scene
from patches import create_patches
from quality_check import check_all_patches
from metadata_writer import write_metadata


def run_pipeline(
    raw_path,
    target_date="2026-08-15",
    patch_size=256
):
    print("=" * 60)
    print("SLICKTRACE MODULE 1 PIPELINE")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. Check raw input
    # ---------------------------------------------------------
    if not os.path.exists(raw_path):
        raise FileNotFoundError(
            f"Raw SAR image not found: {raw_path}"
        )

    print(f"\n[1/4] Raw image found:")
    print(raw_path)

    # ---------------------------------------------------------
    # 2. Preprocess
    # ---------------------------------------------------------
    proc_path = (
        f"data/processed/"
        f"sentinel1_bhatkal_20260815_processed.tif"
    )

    print("\n[2/4] Preprocessing...")
    preprocess_scene(raw_path, proc_path)

    # ---------------------------------------------------------
    # 3. Create patches
    # ---------------------------------------------------------
    patch_dir = "data/patches"

    print("\n[3/4] Creating patches...")

    patches = create_patches(
        proc_path,
        patch_dir,
        patch_size=patch_size
    )

    print(f"Created patches: {len(patches)}")

    # ---------------------------------------------------------
    # 4. Quality check
    # ---------------------------------------------------------
    print("\n[4/4] Running quality checks...")

    qa_results = check_all_patches(
        patch_dir
    )

    passed = sum(
        1 for result in qa_results
        if result["passed"]
    )

    failed = len(qa_results) - passed

    print(
        f"QA result: {passed}/{len(qa_results)} passed"
    )

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------
    metadata = {
        "satellite": "Sentinel-1",
        "collection": "COPERNICUS/S1_GRD",
        "image_id": (
            "S1D_IW_GRDH_1SDV_20260815T004713_"
            "20260815T004738_004129_0078BA_667D"
        ),
        "date": target_date,
        "platform": "Sentinel-1D",
        "polarization": ["VV", "VH"],
        "instrument_mode": "IW",
        "orbit_direction": "DESCENDING",
        "latitude": 13.9,
        "longitude": 74.55,
        "aoi_buffer_km": 25,
        "patch_size": patch_size,
        "num_patches": passed,
        "preprocessing": {
            "conversion": "linear-to-dB",
            "denoise": "median_filter_k5",
            "normalize_range": [0, 1]
        },
        "qa_passed": failed == 0,
        "qa_total": len(qa_results),
        "qa_failed": failed,
        "generated_by": "module1_data/pipeline.py"
    }

    write_metadata(
        metadata,
        target_date
    )

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(f"Raw image:       {raw_path}")
    print(f"Processed image: {proc_path}")
    print(f"Patches:         {passed}")
    print(f"QA failed:       {failed}")
    print("Metadata:        metadata/S1_2026_08_15.json")

    return metadata


if __name__ == "__main__":

    run_pipeline(
        raw_path="data/raw/sentinel1_bhatkal_20260815.tif",
        target_date="2026-08-15",
        patch_size=256
    )