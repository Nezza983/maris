import rasterio
import glob
import numpy as np
import os

print("=" * 70)
print("SLICKTRACE - SAR DATA VALIDATION")
print("=" * 70)

files = glob.glob("data/raw/*.tif")

print(f"\nFound {len(files)} GeoTIFF files\n")

for file in files:

    print("-" * 70)
    print(os.path.basename(file))

    with rasterio.open(file) as src:

        print("Width :", src.width)
        print("Height:", src.height)
        print("Bands :", src.count)
        print("CRS   :", src.crs)

        for band in range(1, src.count + 1):

            data = src.read(band)

            valid = data[np.isfinite(data)]

            if len(valid) == 0:
                print(f"Band {band}: NO VALID DATA")
                continue

            print(
                f"Band {band}: "
                f"min={valid.min():.4f}, "
                f"max={valid.max():.4f}, "
                f"mean={valid.mean():.4f}, "
                f"std={valid.std():.4f}"
            )

print("\n" + "=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)