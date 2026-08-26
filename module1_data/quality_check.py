import rasterio
import numpy as np
import json
import os


def run_quality_check(
    patch_path,
    expected_size=256,
    expected_bands=2
):
    report = {
        "file": patch_path,
        "checks": {},
        "passed": False
    }

    if not os.path.exists(patch_path):
        report["checks"]["exists"] = False
        return report

    report["checks"]["exists"] = True

    try:
        with rasterio.open(patch_path) as src:

            data = src.read()

            checks = {
                "correct_dimensions": bool(
                    src.width == expected_size
                    and src.height == expected_size
                ),

                "correct_band_count": bool(
                    src.count == expected_bands
                ),

                "no_empty_image": bool(
                    not np.all(data == 0)
                ),

                "no_nan_values": bool(
                    not np.isnan(data).any()
                ),

                "values_in_range": bool(
                    np.nanmin(data) >= 0
                    and np.nanmax(data) <= 1
                ),

                "has_crs": bool(
                    src.crs is not None
                ),

                "correct_resolution": bool(
                    abs(src.res[0] - 10.0) < 0.01
                    and abs(src.res[1] - 10.0) < 0.01
                ),

                "correct_band_descriptions": bool(
                    src.descriptions[0] == "VV_normalized"
                    and src.descriptions[1] == "VH_normalized"
                )
            }

            # Calculate zero percentage separately
            zero_fraction = float(
                np.count_nonzero(data == 0)
                / data.size
            )

            checks["no_excessive_zeros"] = bool(
                zero_fraction < 0.30
            )

            report["checks"] = checks

            report["details"] = {
                "width": int(src.width),
                "height": int(src.height),
                "bands": int(src.count),
                "resolution": [
                    float(src.res[0]),
                    float(src.res[1])
                ],
                "crs": str(src.crs),
                "zero_fraction": zero_fraction,
                "min_value": float(np.nanmin(data)),
                "max_value": float(np.nanmax(data))
            }

            report["passed"] = bool(
                all(checks.values())
            )

    except Exception as e:

        report["passed"] = False
        report["error"] = str(e)

    return report


def check_all_patches(
    patch_dir,
    out_report="metadata/qa_report.json"
):

    results = []

    if not os.path.exists(patch_dir):
        print(
            f"ERROR: Directory not found: {patch_dir}"
        )
        return results

    patch_files = sorted(
        fname
        for fname in os.listdir(patch_dir)
        if fname.lower().endswith(".tif")
    )

    print(
        f"Found {len(patch_files)} TIFF patches."
    )

    for fname in patch_files:

        patch_path = os.path.join(
            patch_dir,
            fname
        )

        result = run_quality_check(
            patch_path
        )

        results.append(result)

    passed = sum(
        1
        for result in results
        if result["passed"]
    )

    total = len(results)

    print()
    print(
        f"QA: {passed}/{total} patches passed"
    )

    # Show failed patches
    for result in results:

        if not result["passed"]:

            print()
            print(
                "FAILED:",
                result["file"]
            )

            if "error" in result:
                print(
                    "ERROR:",
                    result["error"]
                )

            for check_name, check_value in result[
                "checks"
            ].items():

                if check_value is False:
                    print(
                        "  FAILED CHECK:",
                        check_name
                    )

    # Create metadata directory
    os.makedirs(
        os.path.dirname(out_report),
        exist_ok=True
    )

    # Save report
    with open(
        out_report,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            results,
            f,
            indent=2
        )

    print()
    print(
        f"QA report saved to: {out_report}"
    )

    return results


if __name__ == "__main__":

    check_all_patches(
        "data/patches/",
        "metadata/qa_report.json"
    )