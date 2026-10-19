# Reproduction and validation

Run commands from the repository root with Python **3.11**:

```bash
python -m pip install -r requirements.txt
```

The pinned NumPy and VTK versions are the environment used for conversion and
validation. PZero is installed separately.

## Well conversion

```bash
python scripts/convert_wells.py
python scripts/validate_wells.py
```

The converter uses the original files in `wells/source_inputs/` and the
coordinate-frame snapshot in `wells/project_frame/`. Outputs go to
`results/wells/`, preserving the supplied reference files in `wells/converted/`.

The independent validator checks source and output hashes, every exported
trajectory station and all 72 markers across CSV, XLSX and VTK. It uses NumPy
interpolation independently of the converter and checks original depths,
marker names and positions under the PZero import algorithm. Numerical
comparisons use explicit tolerances.

See [coordinate definitions](coordinates.md) for the conversion method.

## Project verification

```bash
python scripts/verify_dataset.py --geometry --report results/dataset_validation.json
```

This checks file hashes, sizes and project references; reads all 205 VTK
objects; checks finite coordinates and positive tetrahedron orientation; and
compares the saved well trajectories and 72 markers with the converted data.
Omit `--geometry` for file and project-reference checks only.

The project contains saved interpretation and meshing results. These scripts
reproduce well preprocessing and validate the supplied geometry; manual
interpretation and mesh generation remain PZero/PyMeshIt workflows.

## Seismic volume

The [main README](../README.md#open-the-project) contains the Google Drive
download link. With `final9.p0` open, use **File → Import SEGY**, select the
downloaded file, and choose the existing horizon/fault group in the
**Link interpreted entities** dialog. PZero links the interpretations to the
imported seismic. Save the project to retain these links.

The exact SEG-Y filename, size, SHA-256 and detected trace headers are recorded
in [`metadata/external_data.json`](../metadata/external_data.json).
