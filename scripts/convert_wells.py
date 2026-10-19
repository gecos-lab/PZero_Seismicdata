"""Convert original F3 well tracks and markers into PZero TWT coordinates.

XY: EPSG:23031, metres. Z: negative two-way travel time, milliseconds.
Run from the repository root: python scripts/convert_wells.py
Bundled inputs and a documented coordinate-frame snapshot are the defaults.
Numerical interpolation and sampling follow the original validated converter.
"""
import argparse
from bisect import bisect_right
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
from xml.etree import ElementTree as ET
import zipfile

import vtk

PACKAGE = Path(__file__).resolve().parents[1] / "wells"
WELLS = ("F02-1", "F03-2", "F03-4", "F06-1")
XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def numeric_rows(path, width):
    """Read numeric rows below an OpendTect ASCII header."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        fields = line.split()
        if len(fields) != width:
            continue
        try:
            values = tuple(float(value) for value in fields)
        except ValueError:
            continue
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Non-finite data in {path}")
        rows.append(values)
    if len(rows) < 2:
        raise ValueError(f"At least two numeric rows required: {path}")
    return rows


def require_increasing(values, label):
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError(f"{label} must be strictly increasing")


def interpolate(md, depths, values):
    """Piecewise linear interpolation; extrapolation/clamping is forbidden."""
    if not depths[0] <= md <= depths[-1]:
        raise ValueError(f"MD {md} is outside [{depths[0]}, {depths[-1]}]")
    if md == depths[-1]:
        return values[-1]
    left = max(0, bisect_right(depths, md) - 1)
    fraction = (md - depths[left]) / (depths[left + 1] - depths[left])
    return values[left] + fraction * (values[left + 1] - values[left])


def read_markers(path):
    """The .wlm 'Depth along hole' values are measured depths, not elevations."""
    groups = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"(\d+)\.([^:]+):\s*(.*)$", line)
        if match:
            groups.setdefault(int(match[1]), {})[match[2]] = match[3]
    markers = []
    for marker_id, record in sorted(groups.items()):
        if "Name" not in record or "Depth along hole" not in record:
            raise ValueError(f"Incomplete marker {marker_id} in {path}")
        depth = float(record["Depth along hole"])
        if not math.isfinite(depth):
            raise ValueError(f"Non-finite marker depth in {path}")
        color = tuple(int(v) for v in record.get("Color", "128`128`128").split("`"))
        markers.append({"marker_id": marker_id, "marker": record["Name"],
                        "original_md_m": depth,
                        "strat_level": int(record.get("Strat Level", -1)), "color": color})
    if not markers:
        raise ValueError(f"No markers found: {path}")
    return markers


def snapshot(source, target):
    """Keep existing byte-identical evidence; reject changed originals."""
    source, target = Path(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        if target.exists() and sha256(target) != sha256(source):
            raise ValueError(f"Existing input snapshot differs: {target}")
        if not target.exists():
            shutil.copy2(source, target)
    return {"original_path": "F3_Demo_2023/" + target.relative_to(PACKAGE / "source_inputs").as_posix(),
            "snapshot": target.relative_to(PACKAGE).as_posix(),
            "sha256": sha256(target), "bytes": target.stat().st_size}


def project_frame(project):
    pointer = Path(project).read_text(encoding="utf-8-sig").splitlines()
    revision = pointer[pointer.index("Last saved revision:") + 1]
    root = Path(project).with_name(Path(project).stem + "_p0") / revision
    records = json.loads((root / "image_table.json").read_text())
    candidates = []
    for record in records.values():
        sidecar = root / (record["uid"] + "_seismic_metadata.json")
        if record.get("topology") == "Seismics" and sidecar.is_file():
            payload = json.loads(sidecar.read_text())
            candidates.append((record, payload, sidecar))
    if len(candidates) != 1:
        raise ValueError("Expected one saved seismic metadata sidecar")
    record, payload, sidecar = candidates[0]
    return {"project_file": str(Path(project).resolve()), "revision": revision,
            "seismic_uid": record["uid"], "seismic_name": record["name"],
            "seismic_metadata": payload["seismic_metadata"],
            "pointer_sha256": sha256(project), "sidecar_sha256": sha256(sidecar)}


def validate_frame(frame, survey_path):
    metadata = frame["seismic_metadata"]
    expected = {"vertical_domain": "twt", "vertical_units": "ms", "xy_units": "m",
                "z_positive": "up", "depth_model": "none", "crs": "EPSG:23031"}
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"Unsupported project frame: {key}={metadata.get(key)!r}; expected {value}")
    if metadata.get("import_options", {}).get("negate_z") is not True:
        raise ValueError("Expected negative time coordinates")
    survey = Path(survey_path).read_text(encoding="utf-8-sig")
    if "Coordinate System.Projection.ID: EPSG`23031" not in survey:
        raise ValueError("Original survey CRS does not match the declared project frame")
    if not re.search(r"^Z range: .*`T$", survey, flags=re.MULTILINE):
        raise ValueError("Original F3 survey is not declared as time-domain")


def write_csv(path, records, columns):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def excel_column(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def write_xlsx(path, sheets):
    """Minimal standards-based XLSX, using inline strings and numeric cells."""
    ET.register_namespace("", XLSX_NS)
    workbook = ET.Element(f"{{{XLSX_NS}}}workbook")
    book_sheets = ET.SubElement(workbook, f"{{{XLSX_NS}}}sheets")
    doc_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    rels = ET.Element("Relationships", xmlns=rel_ns)
    ct = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    ET.SubElement(ct, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(ct, "Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(ct, "Override", PartName="/xl/workbook.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    package_rels = ET.Element("Relationships", xmlns=rel_ns)
    ET.SubElement(package_rels, "Relationship", Id="rId1", Type=doc_rel + "/officeDocument", Target="xl/workbook.xml")
    parts = {}
    for i, (name, rows) in enumerate(sheets, 1):
        ET.SubElement(book_sheets, f"{{{XLSX_NS}}}sheet", name=name, sheetId=str(i), **{f"{{{doc_rel}}}id": f"rId{i}"})
        ET.SubElement(rels, "Relationship", Id=f"rId{i}", Type=doc_rel + "/worksheet", Target=f"worksheets/sheet{i}.xml")
        ET.SubElement(ct, "Override", PartName=f"/xl/worksheets/sheet{i}.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
        sheet = ET.Element(f"{{{XLSX_NS}}}worksheet")
        data = ET.SubElement(sheet, f"{{{XLSX_NS}}}sheetData")
        for row_id, values in enumerate(rows, 1):
            row = ET.SubElement(data, f"{{{XLSX_NS}}}row", r=str(row_id))
            for col_id, value in enumerate(values, 1):
                if value is None:
                    continue
                address = excel_column(col_id) + str(row_id)
                if isinstance(value, str):
                    cell = ET.SubElement(row, f"{{{XLSX_NS}}}c", r=address, t="inlineStr")
                    ET.SubElement(ET.SubElement(cell, f"{{{XLSX_NS}}}is"), f"{{{XLSX_NS}}}t").text = value
                else:
                    cell = ET.SubElement(row, f"{{{XLSX_NS}}}c", r=address)
                    ET.SubElement(cell, f"{{{XLSX_NS}}}v").text = repr(value)
        parts[f"xl/worksheets/sheet{i}.xml"] = ET.tostring(sheet, encoding="utf-8", xml_declaration=True)
    parts.update({"[Content_Types].xml": ET.tostring(ct, encoding="utf-8", xml_declaration=True),
                  "_rels/.rels": ET.tostring(package_rels, encoding="utf-8", xml_declaration=True),
                  "xl/workbook.xml": ET.tostring(workbook, encoding="utf-8", xml_declaration=True),
                  "xl/_rels/workbook.xml.rels": ET.tostring(rels, encoding="utf-8", xml_declaration=True)})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in parts.items():
            entry = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, contents)


def vtk_numeric(obj, name, values, integer=False):
    array = vtk.vtkIntArray() if integer else vtk.vtkDoubleArray()
    array.SetName(name)
    for value in values:
        array.InsertNextValue(value)
    obj.GetPointData().AddArray(array)


def vtk_string(obj, name, values, point_data=False):
    array = vtk.vtkStringArray()
    array.SetName(name)
    for value in values:
        array.InsertNextValue(str(value))
    (obj.GetPointData() if point_data else obj.GetFieldData()).AddArray(array)


def write_vtp(path, well, rows, metadata, markers=False):
    obj = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetDataTypeToDouble()
    for row in rows:
        points.InsertNextPoint(row["x_m"], row["y_m"], row["z_twt_ms"])
    obj.SetPoints(points)
    cells = vtk.vtkCellArray()
    if markers:
        for index in range(len(rows)):
            cells.InsertNextCell(1)
            cells.InsertCellPoint(index)
        obj.SetVerts(cells)
        vtk_string(obj, "marker_name", [row["marker"] for row in rows], point_data=True)
        vtk_numeric(obj, "marker_id", [row["marker_id"] for row in rows], integer=True)
        vtk_numeric(obj, "strat_level", [row["strat_level"] for row in rows], integer=True)
    else:
        cells.InsertNextCell(len(rows))
        for index in range(len(rows)):
            cells.InsertCellPoint(index)
        obj.SetLines(cells)
        vtk_numeric(obj, "trace_parameter", [row["trace_parameter"] for row in rows])
        vtk_numeric(obj, "source_track_depth_m", [row["source_track_depth_m"] for row in rows])
    vtk_numeric(obj, "original_md_m", [row["original_md_m"] for row in rows])
    vtk_numeric(obj, "twt_ms", [row["twt_ms"] for row in rows])
    vtk_string(obj, "well_name", [well])
    vtk_string(obj, "pzero_seismic_metadata", [json.dumps(metadata, sort_keys=True)])
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(obj)
    writer.SetDataModeToAscii()
    if not writer.Write() or writer.GetErrorCode():
        raise OSError(f"Could not write {path}")
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    reopened = reader.GetOutput()
    if reopened.GetNumberOfPoints() != len(rows):
        raise ValueError(f"VTP round-trip point count failed: {path}")
    error = max(abs(a-b) for i, row in enumerate(rows)
                for a, b in zip(reopened.GetPoint(i), (row["x_m"], row["y_m"], row["z_twt_ms"])))
    if error > 1e-8:
        raise ValueError(f"VTP coordinate round-trip failed: {path}, {error}")
    return error


def convert_well(well, source, output, frame, spacing):
    track = numeric_rows(source / "WellInfo" / (well + ".well"), 4)
    model = numeric_rows(source / "WellInfo" / (well + ".wlt"), 2)
    markers = read_markers(source / "WellInfo" / (well + ".wlm"))
    track_md = [r[3] for r in track]
    model_md = [r[0] for r in model]
    model_time = [r[1] for r in model]
    require_increasing(track_md, well + " track MD")
    require_increasing(model_md, well + " model MD")
    if any(b < a for a, b in zip(model_time, model_time[1:])):
        raise ValueError(f"{well} model time must not decrease with measured depth")
    # F02-1 has two original equal-time intervals. Preserve them exactly;
    # identical time/XY stations are valid duplicate positions in this frame.
    plateau_count = sum(a == b for a, b in zip(model_time, model_time[1:]))
    lower, upper = max(track_md[0], model_md[0]), min(track_md[-1], model_md[-1])
    if lower != 0 or upper <= lower:
        raise ValueError(f"Expected a valid conversion interval starting at MD 0: {well}")
    for marker in markers:
        if not lower <= marker["original_md_m"] <= upper:
            raise ValueError(f"Marker outside track/model coverage: {well}/{marker['marker']}")
    # Include every model knot and track station, so the piecewise-linear
    # geometry also preserves both changes in velocity and well deviation.
    depth_set = {lower, upper}
    depth_set.update(d for d in model_md + track_md if lower <= d <= upper)
    depth_set.update(marker["original_md_m"] for marker in markers)
    depth_set.update(lower + i * spacing for i in range(int((upper-lower)/spacing)+1))
    depths = sorted(depth_set)
    rows = []
    for md in depths:
        twt_s = interpolate(md, model_md, model_time)
        x = interpolate(md, track_md, [r[0] for r in track])
        y = interpolate(md, track_md, [r[1] for r in track])
        source_depth = interpolate(md, track_md, [r[2] for r in track])
        row = {"well": well, "original_md_m": md, "x_m": x, "y_m": y,
               "source_track_depth_m": source_depth, "twt_s": twt_s,
               "twt_ms": 1000*twt_s, "z_twt_ms": -1000*twt_s}
        previous = rows[-1] if rows else None
        step = math.dist((x, y, row["z_twt_ms"]),
                         (previous["x_m"], previous["y_m"], previous["z_twt_ms"])) if previous else 0
        row["trace_parameter"] = previous["trace_parameter"] + step if previous else 0
        rows.append(row)
    trace_parameters = [r["trace_parameter"] for r in rows]
    if any(b < a for a, b in zip(trace_parameters, trace_parameters[1:])):
        raise ValueError(f"Non-monotonic importer trace parameter: {well}")
    by_md = {row["original_md_m"]: (i, row) for i, row in enumerate(rows)}
    marker_rows = []
    for marker in markers:
        index, row = by_md[marker["original_md_m"]]
        marker_rows.append({**row, **marker, "trace_index": index})
    metadata = dict(frame["seismic_metadata"])
    metadata["well_conversion"] = {
        "well": well, "target_project_revision": frame["revision"],
        "target_seismic_uid": frame["seismic_uid"],
        "input_md_units": "m", "source_time_units": "s", "output_time_units": "ms",
        "source_crs": "EPSG:23031", "target_crs": "EPSG:23031",
        "xy_transform": "identity", "z_recipe": "z_twt_ms = -1000 * interpolate(original_md_m, source_wlt)",
        "source_model": well + ".wlt", "interpolation": "piecewise linear",
        "extrapolation": "forbidden", "original_time_datum": "retained",
        "trace_parameter_units": "mixed-coordinate path distance; not measured depth",
    }
    columns = ["well", "original_md_m", "x_m", "y_m", "source_track_depth_m",
               "twt_s", "twt_ms", "z_twt_ms", "trace_parameter"]
    write_csv(output / (well + "_trajectory.csv"), rows, columns)
    write_csv(output / (well + "_markers.csv"), marker_rows,
              ["well", "marker_id", "marker", "strat_level", "original_md_m", "x_m", "y_m",
               "twt_s", "twt_ms", "z_twt_ms", "trace_parameter", "trace_index"])
    vtp_error = write_vtp(output / (well + "_trajectory.vtp"), well, rows, metadata)
    marker_error = write_vtp(output / (well + "_markers.vtp"), well, marker_rows, metadata, markers=True)
    head = rows[0]
    geometry = [["DX", "DY", "DZ"]] + [[head["x_m"]-r["x_m"], head["y_m"]-r["y_m"],
                head["z_twt_ms"]-r["z_twt_ms"]] for r in rows]
    # The current importer derives an artificial 'MD' from geometric path
    # distance in mixed m/ms coordinates. START/STOP must use that parameter;
    # actual measured depth remains explicitly available as ORIGINAL_MD_m.
    geology = [["START", "STOP", "GEOLOGY"]]
    for index, marker in enumerate(marker_rows):
        stop = marker_rows[index+1]["trace_parameter"] if index+1<len(marker_rows) else rows[-1]["trace_parameter"]
        geology.append([marker["trace_parameter"], stop, marker["marker"]])
    original = [["MD", "ORIGINAL_MD_m", "TWT_ms", "SOURCE_TRACK_DEPTH_m"]]
    original += [[r["trace_parameter"], r["original_md_m"], r["twt_ms"], r["source_track_depth_m"]] for r in rows]
    sheets = [("INFO", [["NAME", "EASTING", "NORTHING", "ELEV", "COORDINATE_METADATA"],
                        [well, head["x_m"], head["y_m"], head["z_twt_ms"], json.dumps(metadata, sort_keys=True)]]),
              ("GEOMETRY", geometry), ("GEOLOGY", geology), ("ORIGINAL_MD", original)]
    write_xlsx(output / (well + "_pzero_well.xlsx"), sheets)
    note = ("ELEV/DZ describe signed time coordinates in ms, not elevation/depth in metres. "
            "The sheet MD and GEOLOGY START/STOP are the importer's mixed-coordinate path parameter, "
            "not physical measured depth; use ORIGINAL_MD_m for the original measured depth.")
    (output / (well + "_coordinate_metadata.json")).write_text(
        json.dumps({"well": well, "seismic_frame": metadata, "workbook_note": note}, indent=2), encoding="utf-8")
    outside = sum(r["twt_ms"] < 4 or r["twt_ms"] > 1848 for r in rows)
    summary = {"well": well, "trajectory_points": len(rows), "markers": len(markers),
               "source_track_last_md_m": track_md[-1], "model_last_md_m": model_md[-1],
               "converted_last_md_m": upper, "unconverted_track_length_md_m": track_md[-1]-upper,
               "min_twt_ms": rows[0]["twt_ms"], "max_twt_ms": rows[-1]["twt_ms"],
               "min_z_ms": rows[-1]["z_twt_ms"], "max_z_ms": rows[0]["z_twt_ms"],
               "points_outside_seismic_4_to_1848_ms": outside,
               "source_equal_time_intervals": plateau_count,
               "zero_length_time_frame_segments": sum(a == b for a, b in zip(trace_parameters, trace_parameters[1:])),
               "vtp_coordinate_roundtrip_error": max(vtp_error, marker_error)}
    return rows, marker_rows, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", type=Path, default=PACKAGE / "source_inputs")
    parser.add_argument("--project", type=Path, help="Optional current PZero project pointer; otherwise use bundled frame")
    parser.add_argument("--out-dir", type=Path, default=PACKAGE.parent / "results" / "wells")
    parser.add_argument("--spacing-md-m", type=float, default=5, help="Additional maximum MD spacing; all model/track/marker knots are also kept")
    args = parser.parse_args(argv)
    if not math.isfinite(args.spacing_md_m) or args.spacing_md_m <= 0:
        parser.error("--spacing-md-m must be finite and positive")
    source = args.source_root.resolve()
    output = args.out_dir.resolve()
    if output == source or source in output.parents:
        raise ValueError("Output must be outside the original source folder")
    frame_dir = PACKAGE / "project_frame"
    frame_dir.mkdir(exist_ok=True)
    context_path = frame_dir / "project_context.json"
    if args.project:
        frame = project_frame(args.project)
        if context_path.exists() and json.loads(context_path.read_text()) != frame:
            raise ValueError("Project frame changed; use a new evidence-package folder")
        context_path.write_text(json.dumps(frame, indent=2), encoding="utf-8")
        shutil.copyfile(args.project, frame_dir / "project_pointer_snapshot.p0")
    else:
        frame = json.loads(context_path.read_text(encoding="utf-8"))
    validate_frame(frame, source / ".survey")
    input_files = [snapshot(source / ".survey", PACKAGE / "source_inputs" / ".survey")]
    for well in WELLS:
        for extension in (".well", ".wlt", ".wlm"):
            input_files.append(snapshot(source / "WellInfo" / (well+extension),
                                        PACKAGE / "source_inputs" / "WellInfo" / (well+extension)))
    # Preserve original source paths in the manifest on portable reruns.
    provenance_path = PACKAGE / "source_inputs" / "provenance.json"
    if provenance_path.exists():
        recorded = json.loads(provenance_path.read_text())
        for record in recorded:
            record["snapshot"] = record["snapshot"].replace("\\", "/")
        if {r["snapshot"]:r["sha256"] for r in recorded} != {r["snapshot"]:r["sha256"] for r in input_files}:
            raise ValueError("Input evidence hashes changed")
        input_files = recorded
        provenance_path.write_text(json.dumps(input_files, indent=2), encoding="utf-8")
    else:
        provenance_path.write_text(json.dumps(input_files, indent=2), encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    all_markers, summary = [], []
    for well in WELLS:
        _, markers, row = convert_well(well, source, output, frame, args.spacing_md_m)
        all_markers.extend(markers)
        summary.append(row)
        print(f"{well}: {row['trajectory_points']} trajectory points, {row['markers']} markers; "
              f"MD <= {row['converted_last_md_m']:.6f} m, Z = -TWT_ms", flush=True)
    write_csv(output / "well_conversion_summary.csv", summary, list(summary[0]))
    write_csv(output / "all_well_markers.csv", all_markers,
              ["well", "marker_id", "marker", "strat_level", "original_md_m", "x_m", "y_m",
               "twt_s", "twt_ms", "z_twt_ms", "trace_parameter", "trace_index"])
    generated = [{"file": p.name, "sha256": sha256(p), "bytes": p.stat().st_size}
                 for p in sorted(output.iterdir()) if p.is_file() and p.name not in ("conversion_manifest.json", "validation_report.json")]
    manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                "converter_sha256": sha256(__file__), "python_version": sys.version,
                "vtk_version": vtk.vtkVersion.GetVTKVersion(), "project_frame": frame,
                "source_files": input_files, "spacing_md_m": args.spacing_md_m,
                "xy_recipe": "identity: EPSG:23031 metres", "z_recipe": "-1000 * well_specific_wlt_TWT_seconds",
                "datum": "original well model time datum retained; no added 4 ms sample-origin offset",
                "extrapolation": "none; trajectory limited to shared track/model MD coverage",
                "sampling": "union of model knots, track knots, marker MDs, endpoints, regular MD stations",
                "scope": "well trajectories and stratigraphic markers; original geophysical log curves are not exported",
                "project_revision_modified": False, "summary": summary, "generated_files": generated}
    (output / "conversion_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(summary)} wells and {len(all_markers)} markers to {output}", flush=True)


if __name__ == "__main__":
    main()
