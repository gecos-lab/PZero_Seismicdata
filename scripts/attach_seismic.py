"""Create a working final9 copy referencing the separately downloaded F3 SEG-Y.

The supplied project stays unchanged. Its original seismic UID is restored
so interpreted objects retain their associations without coordinate rescaling.
PZero performs its normal validated SEG-Y import when this working copy opens.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil

from verify_dataset import ROOT, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--segy",
        required=True,
        type=Path,
        help="Exact F3 SEG-Y specified in metadata/external_data.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "results" / "final9_with_seismic"
    )
    args = parser.parse_args()
    seismic = args.segy.resolve(strict=True)
    external = json.loads((ROOT / "metadata" / "external_data.json").read_text())[
        "f3_seismic"
    ]
    if (
        seismic.stat().st_size != external["bytes"]
        or sha256(seismic) != external["sha256"]
    ):
        raise ValueError(
            "SEG-Y differs from the F3 file used by this project. Select the file identified in metadata/external_data.json."
        )
    if args.output_dir.exists():
        raise FileExistsError(f"Output folder already exists: {args.output_dir}")
    source = ROOT / "final9"
    if args.output_dir.resolve().is_relative_to(source.resolve()):
        raise ValueError("Working copy must be outside the supplied final9 folder")
    lines = (source / "final9.p0").read_text().splitlines()
    revision = lines[lines.index("Last saved revision:") + 1]
    source_revision = source / "final9_p0" / revision
    if json.loads((source_revision / "image_table.json").read_text()):
        raise ValueError("The supplied project already contains an image collection")
    shutil.copytree(source, args.output_dir)
    destination = args.output_dir / "final9_p0" / revision
    context = json.loads(
        (ROOT / "wells" / "project_frame" / "project_context.json").read_text()
    )
    metadata = deepcopy(context["seismic_metadata"])
    metadata["source_file"] = str(seismic)
    metadata["source_identity"] = {
        "size": seismic.stat().st_size,
        "mtime_ns": seismic.stat().st_mtime_ns,
    }
    uid = context["seismic_uid"]
    image = {
        "uid": uid,
        "name": context["seismic_name"],
        "scenario": "undef",
        "parent_uid": "",
        "topology": "Seismics",
        "properties_names": ["intensity"],
        "properties_components": [1],
        "properties_types": ["float"],
        "seismic_source_file": str(seismic),
    }
    (destination / "image_table.json").write_text(
        json.dumps({"0": image}, indent=2) + "\n", encoding="utf-8"
    )
    sidecar = {
        "uid": uid,
        "source_file": str(seismic),
        "storage": "source_file",
        "seismic_metadata": metadata,
    }
    (destination / (uid + "_seismic_metadata.json")).write_text(
        json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Open in PZero: {args.output_dir / 'final9.p0'}\nSeismic UID restored: {uid}\nThe supplied project and interpreted coordinates are unchanged."
    )


if __name__ == "__main__":
    main()
