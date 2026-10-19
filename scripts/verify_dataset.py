"""Verify dataset files; optionally inspect every VTK dataset."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "metadata" / "manifest.json"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_files():
    files = []
    for folder in ("final9", "wells", "scripts", "docs", "metadata"):
        files.extend(
            path
            for path in (ROOT / folder).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    files.extend(
        ROOT / name
        for name in (
            "README.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "requirements.txt",
            ".gitignore",
            ".gitattributes",
        )
    )
    excluded = {MANIFEST, ROOT / "metadata" / "SHA256SUMS"}
    return sorted(path for path in files if path.exists() and path not in excluded)


def write_manifest():
    records = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in package_files()
    ]
    MANIFEST.write_text(
        json.dumps({"format_version": 1, "files": records}, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [f"{record['sha256']}  {record['path']}" for record in records]
    lines.append(f"{sha256(MANIFEST)}  metadata/manifest.json")
    (ROOT / "metadata" / "SHA256SUMS").write_text(
        "\n".join(sorted(lines)) + "\n", encoding="utf-8"
    )
    return records


def project_tables():
    pointer = ROOT / "final9" / "final9.p0"
    lines = pointer.read_text(encoding="utf-8").splitlines()
    revision = lines[lines.index("Last saved revision:") + 1]
    folder = pointer.parent / "final9_p0" / revision
    tables = {
        name: list(json.loads((folder / (name + "_table.json")).read_text()).values())
        for name in ("geological", "mesh3d", "well", "boundary", "image")
    }
    return revision, folder, tables


def geometry_checks(folder, tables):
    import numpy as np
    from vtk import vtkXMLPolyDataReader, vtkXMLUnstructuredGridReader
    from vtkmodules.util.numpy_support import vtk_to_numpy

    checked = 0
    mesh_stats = []
    wells = []
    well_objects = {}
    for collection, rows in tables.items():
        for row in rows:
            extension = ".vtu" if row["topology"] == "TetraSolid" else ".vtp"
            reader = (
                vtkXMLUnstructuredGridReader()
                if extension == ".vtu"
                else vtkXMLPolyDataReader()
            )
            reader.SetFileName(str(folder / (row["uid"] + extension)))
            reader.Update()
            obj = reader.GetOutput()
            if reader.GetErrorCode() or not obj.GetNumberOfPoints():
                raise ValueError(f"Unreadable or empty geometry: {row['name']}")
            points = vtk_to_numpy(obj.GetPoints().GetData())
            if not np.isfinite(points).all():
                raise ValueError(f"Nonfinite coordinates: {row['name']}")
            if collection == "mesh3d":
                cell_types = vtk_to_numpy(obj.GetCellTypesArray())
                if not np.all(cell_types == 10):
                    raise ValueError(f"Non-tetrahedral cells in {row['name']}")
                ids = vtk_to_numpy(obj.GetCells().GetConnectivityArray()).reshape(-1, 4)
                if ids.min() < 0 or ids.max() >= len(points):
                    raise ValueError(f"Invalid connectivity: {row['name']}")
                a, b, c = (points[ids[:, i]] - points[ids[:, 0]] for i in (1, 2, 3))
                signed_volume = np.einsum("ij,ij->i", np.cross(a, b), c) / 6
                if not np.all(signed_volume > 0):
                    raise ValueError(f"Inverted/degenerate tetrahedra: {row['name']}")
                labels = vtk_to_numpy(obj.GetCellData().GetArray("MaterialID"))
                values, counts = np.unique(labels, return_counts=True)
                mesh_stats.append(
                    {
                        "name": row["name"],
                        "points": len(points),
                        "tetrahedra": len(ids),
                        "inverted_or_degenerate": 0,
                        "materials": {str(v): int(n) for v, n in zip(values, counts)},
                    }
                )
            if collection == "well":
                with (
                    ROOT / "wells" / "converted" / (row["name"] + "_trajectory.csv")
                ).open(encoding="utf-8") as stream:
                    trajectory = list(csv.DictReader(stream))
                expected = np.array(
                    [
                        [float(value[key]) for key in ("x_m", "y_m", "z_twt_ms")]
                        for value in trajectory
                    ]
                )
                np.testing.assert_allclose(points, expected, rtol=0, atol=1e-8)
                time_array = obj.GetPointData().GetArray("TWT_ms")
                md_array = obj.GetPointData().GetArray("ORIGINAL_MD_m")
                # Historical WellTrace objects store per-station arrays in field data.
                if time_array is None:
                    time_array = obj.GetFieldData().GetArray("TWT_ms")
                if md_array is None:
                    md_array = obj.GetFieldData().GetArray("ORIGINAL_MD_m")
                if time_array is None or md_array is None:
                    raise ValueError(f"Missing original depth/time samples: {row['name']}")
                time = vtk_to_numpy(time_array).reshape(-1)
                original_md = vtk_to_numpy(md_array).reshape(-1)
                np.testing.assert_allclose(points[:, 2], -time, rtol=0, atol=1e-8)
                np.testing.assert_allclose(
                    original_md,
                    [float(v["original_md_m"]) for v in trajectory],
                    rtol=0,
                    atol=1e-8,
                )
                wells.append(
                    {
                        "name": row["name"],
                        "stations": len(points),
                        "matches_reproduced_conversion": True,
                    }
                )
                well_objects[row["uid"]] = (row["name"], points.copy())
            checked += 1
    marker_count = 0
    for row in tables["geological"]:
        if row["topology"] != "VertexSet" or row.get("parent_uid") not in well_objects:
            continue
        well_name, _ = well_objects[row["parent_uid"]]
        with (ROOT / "wells" / "converted" / (well_name + "_markers.csv")).open(
            encoding="utf-8"
        ) as stream:
            markers = list(csv.DictReader(stream))
        match = [m for m in markers if "marker_" + m["marker"] == row["name"]]
        if len(match) != 1:
            raise ValueError(f"Ambiguous marker identity: {well_name}/{row['name']}")
        reader = vtkXMLPolyDataReader()
        reader.SetFileName(str(folder / (row["uid"] + ".vtp")))
        reader.Update()
        expected = [float(match[0][key]) for key in ("x_m", "y_m", "z_twt_ms")]
        np.testing.assert_allclose(
            reader.GetOutput().GetPoint(0), expected, rtol=0, atol=1e-8
        )
        marker_count += 1
    if marker_count != 72:
        raise ValueError(f"Expected 72 well markers, found {marker_count}")
    return {
        "vtk_objects_checked": checked,
        "well_markers_checked": marker_count,
        "wells": wells,
        "tetrahedral_meshes": mesh_stats,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Maintainer: refresh checksums after reviewed changes",
    )
    parser.add_argument(
        "--geometry",
        action="store_true",
        help="Also validate VTK geometry, tetrahedra and saved well coordinates",
    )
    parser.add_argument(
        "--report", type=Path, help="Optional JSON report, normally under results/"
    )
    args = parser.parse_args()
    records = (
        write_manifest()
        if args.write_manifest
        else json.loads(MANIFEST.read_text())["files"]
    )
    for record in records:
        path = ROOT / record["path"]
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Manifest path escapes the repository")
        if (
            not path.is_file()
            or path.stat().st_size != record["bytes"]
            or sha256(path) != record["sha256"]
        ):
            raise ValueError(f"Checksum mismatch or missing file: {record['path']}")
    actual = {path.relative_to(ROOT).as_posix() for path in package_files()}
    if actual != {r["path"] for r in records}:
        raise ValueError(
            "Package inventory changed; review changes before refreshing the manifest"
        )
    revision, folder, tables = project_tables()
    for rows in tables.values():
        for row in rows:
            extension = ".vtu" if row["topology"] == "TetraSolid" else ".vtp"
            if not (folder / (row["uid"] + extension)).is_file():
                raise ValueError(f"Missing project geometry for {row['name']}")
    report = {
        "status": "passed",
        "files_verified": len(records),
        "bytes_verified": sum(r["bytes"] for r in records),
        "project_revision": revision,
        "entity_counts": {k: len(v) for k, v in tables.items()},
        "geological_topologies": dict(
            Counter(r["topology"] for r in tables["geological"])
        ),
        "seismic_included": bool(tables["image"]),
    }
    if args.geometry:
        report["geometry"] = geometry_checks(folder, tables)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
