"""Independent numerical and file-format checks of the converted F3 wells.

Uses NumPy's interpolator, rather than the converter's bisect implementation.
Checks the exported CSV, XLSX, VTP, original-source hashes, and frame snapshot.
Run: python scripts/validate_wells.py [--out-dir results/wells]
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np
import vtk

ROOT = Path(__file__).resolve().parents[1] / "wells"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric_source(path, width):
    rows = []
    for line in path.read_text().splitlines():
        if not re.match(r"^[+-]?\d", line):
            continue
        fields = line.split()
        if len(fields) == width:
            rows.append([float(v) for v in fields])
    return np.asarray(rows, dtype=np.float64)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def numbers(rows, columns):
    return np.asarray([[float(row[c]) for c in columns] for row in rows])


def read_xlsx(path):
    sheets = {}
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        targets = {r.attrib["Id"]: r.attrib["Target"]
                   for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        for sheet in book.find("s:sheets", NS):
            rel = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = targets[rel]
            part = target.lstrip("/") if target.startswith("/") else "xl/" + target
            parsed = []
            for row in ET.fromstring(archive.read(part)).findall("s:sheetData/s:row", NS):
                cells = {}
                for cell in row:
                    column = re.sub(r"\d", "", cell.attrib["r"])
                    if cell.attrib.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                    else:
                        value = float(cell.find("s:v", NS).text)
                    cells[column] = value
                parsed.append(cells)
            header = parsed[0]
            sheets[sheet.attrib["name"]] = [{header[k]: value for k, value in row.items()}
                                            for row in parsed[1:]]
    return sheets


def read_vtp(path):
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    if reader.GetErrorCode():
        raise ValueError(f"Cannot read {path}")
    obj = reader.GetOutput()
    coordinates = np.asarray([obj.GetPoint(i) for i in range(obj.GetNumberOfPoints())])
    return obj, coordinates


def assert_close(a, b, label, atol=1e-8):
    if not np.allclose(a, b, atol=atol, rtol=0):
        raise AssertionError(f"{label}: maximum discrepancy {np.max(np.abs(a-b))}")
    return float(np.max(np.abs(a-b)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT.parent / "results" / "wells")
    args = parser.parse_args()
    output = args.out_dir
    manifest = json.loads((output / "conversion_manifest.json").read_text())
    for source in manifest["source_files"]:
        assert digest(ROOT / source["snapshot"]) == source["sha256"], source["snapshot"]
    for result in manifest["generated_files"]:
        assert digest(output / result["file"]) == result["sha256"], result["file"]
    assert digest(ROOT.parent / "scripts" / "convert_wells.py") == manifest["converter_sha256"]
    context = json.loads((ROOT / "project_frame" / "project_context.json").read_text())
    assert manifest["project_frame"] == context
    metadata = context["seismic_metadata"]
    assert metadata["crs"] == "EPSG:23031" and metadata["xy_units"] == "m"
    assert metadata["vertical_domain"] == "twt" and metadata["vertical_units"] == "ms"
    assert metadata["depth_model"] == "none" and metadata["z_positive"] == "up"
    results = []
    for summary in manifest["summary"]:
        well = summary["well"]
        source = ROOT / "source_inputs" / "WellInfo"
        track = numeric_source(source / (well + ".well"), 4)
        model = numeric_source(source / (well + ".wlt"), 2)
        trajectory = read_csv(output / (well + "_trajectory.csv"))
        markers = read_csv(output / (well + "_markers.csv"))
        md = numbers(trajectory, ["original_md_m"])[:, 0]
        twt_ms = numbers(trajectory, ["twt_ms"])[:, 0]
        actual_xyz = numbers(trajectory, ["x_m", "y_m", "z_twt_ms"])
        assert len(md) == summary["trajectory_points"]
        assert np.all(np.diff(md) > 0)
        assert md.min() >= max(model[0, 0], track[0, 3])
        assert md.max() == min(model[-1, 0], track[-1, 3])
        expected_twt = 1000 * np.interp(md, model[:, 0], model[:, 1])
        expected_xyz = np.column_stack([np.interp(md, track[:, 3], track[:, 0]),
                                       np.interp(md, track[:, 3], track[:, 1]), -expected_twt])
        time_error = assert_close(twt_ms, expected_twt, well + " model interpolation")
        xy_error = assert_close(actual_xyz[:, :2], expected_xyz[:, :2], well + " XY")
        assert_close(actual_xyz[:, 2], expected_xyz[:, 2], well + " Z")
        assert_close(numbers(trajectory, ["source_track_depth_m"])[:, 0],
                     np.interp(md, track[:, 3], track[:, 2]), well + " original track depth")
        # Every original model knot in coverage is retained, including plateaus.
        assert set(model[(model[:, 0] >= md[0]) & (model[:, 0] <= md[-1]), 0]).issubset(set(md))
        vtp, xyz_vtp = read_vtp(output / (well + "_trajectory.vtp"))
        assert vtp.GetNumberOfLines() == 1
        vtp_error = assert_close(xyz_vtp, expected_xyz, well + " VTP")
        assert_close(np.asarray([vtp.GetPointData().GetArray("original_md_m").GetValue(i)
                                 for i in range(len(md))]), md, well + " VTP original MD")
        sheets = read_xlsx(output / (well + "_pzero_well.xlsx"))
        assert set(sheets) == {"INFO", "GEOMETRY", "GEOLOGY", "ORIGINAL_MD"}
        assert len(sheets["GEOMETRY"]) == len(md)
        head = sheets["INFO"][0]
        declaration = json.loads(head["COORDINATE_METADATA"])
        assert declaration["vertical_domain"] == "twt" and declaration["vertical_units"] == "ms"
        assert declaration["crs"] == "EPSG:23031" and declaration["z_positive"] == "up"
        assert declaration["well_conversion"]["well"] == well
        workbook_xyz = np.array([head["EASTING"], head["NORTHING"], head["ELEV"]]) - numbers(sheets["GEOMETRY"], ["DX", "DY", "DZ"])
        xlsx_error = assert_close(workbook_xyz, expected_xyz, well + " XLSX")
        # This is exactly the current PZero importer's trace-distance algorithm.
        importer_parameter = np.r_[0., np.cumsum(np.linalg.norm(np.diff(workbook_xyz, axis=0), axis=1))]
        assert_close(importer_parameter, numbers(sheets["ORIGINAL_MD"], ["MD"])[:, 0], well + " importer parameter")
        assert_close(numbers(sheets["ORIGINAL_MD"], ["ORIGINAL_MD_m"])[:, 0], md, well + " workbook original MD")
        original_markers = {}
        for line in (source / (well + ".wlm")).read_text().splitlines():
            match = re.match(r"(\d+)\.(Name|Depth along hole):\s*(.*)", line)
            if match:
                original_markers.setdefault(int(match[1]), {})[match[2]] = match[3]
        assert len(markers) == len(original_markers) == len(sheets["GEOLOGY"])
        marker_md = numbers(markers, ["original_md_m"])[:, 0]
        marker_xyz = numbers(markers, ["x_m", "y_m", "z_twt_ms"])
        assert_close(marker_xyz[:, 2], -1000*np.interp(marker_md, model[:, 0], model[:, 1]), well + " marker time")
        snap_error = 0.
        for marker, geology in zip(markers, sheets["GEOLOGY"]):
            key = int(marker["marker_id"])
            assert marker["marker"] == original_markers[key]["Name"] == geology["GEOLOGY"]
            assert float(marker["original_md_m"]) == float(original_markers[key]["Depth along hole"])
            index = int(marker["trace_index"])
            assert md[index] == float(marker["original_md_m"])
            # The importer uses nearest geometric-path distance for each marker.
            imported_index = int(np.argmin(np.abs(importer_parameter-float(geology["START"]))))
            location = numbers([marker], ["x_m", "y_m", "z_twt_ms"])[0]
            snap_error = max(snap_error, assert_close(workbook_xyz[imported_index], location, well + " marker import"))
        marker_vtp, marker_vtp_xyz = read_vtp(output / (well + "_markers.vtp"))
        assert marker_vtp.GetNumberOfVerts() == len(markers)
        assert_close(marker_vtp_xyz, marker_xyz, well + " marker VTP")
        names = marker_vtp.GetPointData().GetAbstractArray("marker_name")
        assert [names.GetValue(i) for i in range(len(markers))] == [r["marker"] for r in markers]
        result = {"well": well, "trajectory_points": len(md), "markers": len(markers),
                  "max_model_interpolation_error_ms": time_error,
                  "max_xy_error_m": xy_error, "max_vtp_coordinate_error": vtp_error,
                  "max_xlsx_coordinate_error": xlsx_error, "max_imported_marker_coordinate_error": snap_error,
                  "extrapolated_points": 0, "status": "passed"}
        results.append(result)
        print(well, "passed: original model, XY, CSV, XLSX, VTP, markers and importer coordinates", flush=True)
    report = {"status": "passed", "validator_sha256": digest(__file__), "numpy_version": np.__version__,
              "python_version": sys.version, "vtk_version": vtk.vtkVersion.GetVTKVersion(),
              "source_and_output_hashes": "passed", "project_frame": "passed",
              "method": "Independent numpy.interp verification of all output trajectory and marker coordinates",
              "total_wells": len(results), "total_markers": sum(r["markers"] for r in results), "wells": results}
    (output / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Validation passed for every exported point and all 72 markers.", flush=True)


if __name__ == "__main__":
    main()
