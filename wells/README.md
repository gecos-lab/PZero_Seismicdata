# F3 well inputs and conversion outputs

Wells **F02-1, F03-2, F03-4, and F06-1** each have 18 stratigraphic markers
(72 total).

## Original inputs

`source_inputs/WellInfo/` holds exactly three original files per well:

- `.well`: horizontal coordinates, track depth and measured depth;
- `.wlt`: supplied measured-depth–two-way-time relationship;
- `.wlm`: marker names, measured depths, colours and source IDs.

`source_inputs/.survey` records the CRS, sampling, time domain and licence.
Input bytes are unchanged; hashes and source-relative paths are in
`source_inputs/provenance.json`. Geophysical log curves are not inputs to this
trajectory/marker conversion.

## Reference outputs

| File in `converted/` | Purpose |
| --- | --- |
| `*_pzero_well.xlsx` | PZero workbook with INFO, GEOMETRY, GEOLOGY and ORIGINAL_MD sheets |
| `*_coordinate_metadata.json` | Coordinate declaration and conversion provenance |
| `*_trajectory.csv`, `*_trajectory.vtp` | Trajectory, original measured depth and time samples |
| `*_markers.csv`, `*_markers.vtp` | Source markers and exact trajectory positions |

Combined markers, conversion summary, generated-file manifest and independent
validation report are also included.

From the repository root, reproduce under `results/wells/`:

```bash
python scripts/convert_wells.py
python scripts/validate_wells.py
```

The numerical method is unchanged from the original validated converter.
Repository adaptations make paths portable, rename `_final7_well.xlsx` to
`_pzero_well.xlsx`, and direct default reruns to `results/`. The frame snapshot
was originally established for final7; `verify_dataset.py --geometry` compares
the saved final9 wells and markers against the reproduced coordinates.

Workbook ELEV/DZ are signed time coordinates in milliseconds. Generic MD is an
importer path parameter in mixed metre/time geometry. Use **ORIGINAL_MD_m** for
physical measured depth. See [coordinates](../docs/coordinates.md) for details.
