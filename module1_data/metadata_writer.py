import json
import os


def write_metadata(meta_dict, scene_date):
    """
    Save standardized Module 1 metadata.
    """

    os.makedirs("metadata", exist_ok=True)

    out_path = (
        f"metadata/S1_{scene_date.replace('-', '_')}.json"
    )

    with open(
        out_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            meta_dict,
            f,
            indent=2
        )

    print(
        f"Metadata saved to: {out_path}"
    )

    return out_path