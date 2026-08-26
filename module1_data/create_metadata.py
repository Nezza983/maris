from metadata_writer import write_metadata


metadata = {
    "satellite": "Sentinel-1",
    "collection": "COPERNICUS/S1_GRD",

    "image_id": (
        "S1D_IW_GRDH_1SDV_20260815T004713_"
        "20260815T004738_004129_0078BA_667D"
    ),

    "date": "2026-08-15",

    "platform": "Sentinel-1D",

    "polarization": [
        "VV",
        "VH"
    ],

    "instrument_mode": "IW",

    "orbit_direction": "DESCENDING",

    "latitude": 13.9,

    "longitude": 74.55,

    "aoi_buffer_km": 25,

    "patch_size": 256,

    "num_patches": 360,

    "resolution_m": 10,

    "preprocessing": {
        "conversion": "linear-to-dB",
        "denoise": "median_filter_k5",
        "normalize_range": [
            0,
            1
        ]
    },

    "qa_passed": True,

    "rejected_patches": 1,

    "rejected_patch": (
        "sentinel1_bhatkal_20260815_processed_007.tif"
    ),

    "generated_by": "module1_data/pipeline.py"
}


write_metadata(
    metadata,
    "2026-08-15"
)