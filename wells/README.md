# Well conversion

The files cover four wells: **F02-1, F03-2, F03-4 and F06-1**.

## Inputs

Each well has three files in `source_inputs/WellInfo/`:

- `.well`: well trajectory.
- `.wlt`: measured-depth to two-way travel-time relationship.
- `.wlm`: stratigraphic markers.

`source_inputs/.survey` contains the survey information.
`coordinate_system.json` supplies the coordinate settings used by the scripts.

## Convert

From the repository root, using Python 3.11:

```bash
python -m pip install -r requirements.txt
python scripts/convert_wells.py
```

Outputs are written to `results/wells/`. The supplied converted files are in
`wells/converted/`.

| Output | Contents |
| --- | --- |
| `*_pzero_well.xlsx` | Workbook ready to import into PZero |
| `*_trajectory.csv`, `*_trajectory.vtp` | Well trajectory |
| `*_markers.csv`, `*_markers.vtp` | Stratigraphic marker positions |
| `*_coordinate_metadata.json` | Coordinate information used during import |

A combined marker table, conversion summary and file manifest are also written.

## Import into PZero

Choose **File > Import Well Data** and select the well's `*_pzero_well.xlsx`
workbook.

## Check the results

```bash
python scripts/validate_wells.py
```

This checks the converted trajectories and all 72 markers, and writes
`results/wells/validation_report.json`.
