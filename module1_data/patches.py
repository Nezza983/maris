import rasterio
from rasterio.windows import Window
import numpy as np
import os


def create_patches(
    in_path,
    out_dir,
    patch_size=256,
    stride=None,
    min_valid_frac=0.7
):
    """
    Tile a processed Sentinel-1 scene into fixed-size patches.

    Parameters
    ----------
    in_path : str
        Input processed GeoTIFF.

    out_dir : str
        Directory where patches will be saved.

    patch_size : int
        Width and height of each patch.

    stride : int or None
        Distance between patches.
        Defaults to patch_size (no overlap).

    min_valid_frac : float
        Minimum fraction of valid pixels required
        for a patch to be saved.
    """

    stride = stride or patch_size

    os.makedirs(
        out_dir,
        exist_ok=True
    )

    with rasterio.open(in_path) as src:

        width = src.width
        height = src.height

        profile = src.profile.copy()

        scene_id = os.path.splitext(
            os.path.basename(in_path)
        )[0]

        patch_id = 0
        saved_paths = []

        print("Input scene:", scene_id)
        print("Width:", width)
        print("Height:", height)
        print("Bands:", src.count)
        print("Patch size:", patch_size)
        print("Stride:", stride)

        for top in range(
            0,
            height - patch_size + 1,
            stride
        ):

            for left in range(
                0,
                width - patch_size + 1,
                stride
            ):

                window = Window(
                    left,
                    top,
                    patch_size,
                    patch_size
                )

                patch = src.read(
                    window=window
                )

                # Calculate fraction of valid pixels
                valid_frac = np.mean(
                    np.isfinite(patch)
                )

                if valid_frac < min_valid_frac:
                    continue

                patch_id += 1

                out_path = os.path.join(
                    out_dir,
                    f"{scene_id}_{patch_id:03d}.tif"
                )

                patch_profile = profile.copy()

                patch_profile.update(
                    width=patch_size,
                    height=patch_size,
                    transform=rasterio.windows.transform(
                        window,
                        src.transform
                    )
                )

                # Replace NaN values with zero
                patch_clean = np.nan_to_num(
                    patch,
                    nan=0.0
                )

                with rasterio.open(
                    out_path,
                    'w',
                    **patch_profile
                ) as dst:

                    dst.write(
                        patch_clean
                    )

                    dst.set_band_description(
                        1,
                        "VV_normalized"
                    )

                    dst.set_band_description(
                        2,
                        "VH_normalized"
                    )

                saved_paths.append(
                    out_path
                )

        print(
            f"\nCreated {len(saved_paths)} patches "
            f"from {scene_id}"
        )

        return saved_paths


if __name__ == '__main__':

    create_patches(
        'data/processed/'
        'sentinel1_bhatkal_20260815_processed.tif',

        'data/patches/',

        patch_size=256
    )