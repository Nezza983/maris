import os

import rasterio
import numpy as np
import cv2


def mask_invalid(band, lower=-30, upper=5):
    """
    Mask obvious invalid/extreme SAR backscatter values.

    The Sentinel-1 GRD data exported from Earth Engine is already
    calibrated in dB, so we work directly in dB here.
    """

    mask = (band > lower) & (band < upper)

    band_clean = np.where(
        mask,
        band,
        np.nan
    )

    return band_clean, mask


def denoise(band, ksize=5):
    """
    Apply a light median filter to reduce speckle.

    NaN pixels are temporarily replaced with the median of
    valid pixels before filtering.
    """

    valid_values = band[np.isfinite(band)]

    if valid_values.size == 0:
        raise ValueError(
            "No valid pixels found in this band."
        )

    fill_value = np.median(valid_values)

    band_filled = np.nan_to_num(
        band,
        nan=fill_value
    )

    return cv2.medianBlur(
        band_filled.astype(np.float32),
        ksize
    )


def normalize(band, out_range=(0, 1)):
    """
    Normalize the band using the 1st and 99th percentiles.

    This reduces the influence of extreme SAR values.
    """

    valid_values = band[np.isfinite(band)]

    if valid_values.size == 0:
        raise ValueError(
            "No valid pixels available for normalization."
        )

    b_min = np.percentile(
        valid_values,
        1
    )

    b_max = np.percentile(
        valid_values,
        99
    )

    if b_max <= b_min:
        raise ValueError(
            "Invalid normalization range."
        )

    band_clipped = np.clip(
        band,
        b_min,
        b_max
    )

    norm = (
        (band_clipped - b_min)
        / (b_max - b_min)
    )

    lo, hi = out_range

    return norm * (hi - lo) + lo


def preprocess_scene(in_path, out_path):

    print("Reading raw SAR image:")
    print(in_path)

    with rasterio.open(in_path) as src:

        profile = src.profile.copy()

        vv = src.read(1)
        vh = src.read(2)

        print("Input CRS:", src.crs)
        print("Input size:", src.width, "x", src.height)
        print("Input bands:", src.count)
        print("Input resolution:", src.res)

    processed_bands = []

    for name, band in [
        ("VV", vv),
        ("VH", vh)
    ]:

        print(f"\nProcessing {name}...")

        # 1. Data is already in dB.
        db = band.astype(np.float32)

        print(
            "Original range:",
            np.nanmin(db),
            "to",
            np.nanmax(db)
        )

        # 2. Remove obvious invalid/extreme pixels
        clean, mask = mask_invalid(
            db,
            lower=-30,
            upper=5
        )

        print(
            "Valid pixels:",
            np.sum(mask),
            "/",
            mask.size
        )

        # 3. Light speckle reduction
        smooth = denoise(
            clean,
            ksize=5
        )

        # 4. Normalize to 0-1
        norm = normalize(
            smooth,
            out_range=(0, 1)
        )

        processed = norm.astype(
            np.float32
        )

        print(
            "Normalized range:",
            np.nanmin(processed),
            "to",
            np.nanmax(processed)
        )

        processed_bands.append(
            processed
        )

    # Preserve geographic metadata
    profile.update(
        dtype=rasterio.float32,
        count=2,
        nodata=None
    )

    os.makedirs(
        os.path.dirname(out_path),
        exist_ok=True
    )

    with rasterio.open(
        out_path,
        'w',
        **profile
    ) as dst:

        dst.write(
            processed_bands[0],
            1
        )

        dst.write(
            processed_bands[1],
            2
        )

        dst.set_band_description(
            1,
            "VV_normalized"
        )

        dst.set_band_description(
            2,
            "VH_normalized"
        )

    print(
        f"\nProcessed image saved to:\n{out_path}"
    )

    return out_path


if __name__ == '__main__':

    preprocess_scene(
        'data/raw/sentinel1_bhatkal_20260815.tif',
        'data/processed/sentinel1_bhatkal_20260815_processed.tif'
    )