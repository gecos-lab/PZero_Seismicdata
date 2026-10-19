# PZero F3 seismic interpretation and meshing dataset

PZero project files and well-conversion scripts for the F3 North Sea dataset.
The **final9** project contains geological interpretations, surfaces, four
well trajectories with 72 markers, a model boundary and tetrahedral meshes.

## Open the project

Open [`final9/final9.p0`](final9/final9.p0) in
[PZero](https://github.com/gecos-lab/PZero). Keep the companion `final9_p0/`
folder beside it. The saved interpretations and meshes open without the
seismic volume.

**F3 seismic (SEG-Y): [Download from Google Drive](https://drive.google.com/drive/folders/0B7brcf-eGK8CbGhBdmZoUnhiTWs?resourcekey=0-0ZhV_OJ3TKN1ShFAGcrOzQ).**

To display the seismic with the model:

1. Download `Dutch Government_F3_entire_8bit seismic.segy` using the link above.
2. With `final9.p0` open in PZero, choose **File → Import SEGY** and select the file.
3. After import, the **Link interpreted entities** dialog appears. Select the
   existing horizon/fault interpretation group and confirm. PZero links those
   interpretations to the newly imported seismic automatically.
4. Save the project to retain the seismic and its interpretation links.

## Contents

| Location | Contents |
| --- | --- |
| [`final9/`](final9/) | Complete saved PZero project, interpretations and meshes |
| [`wells/source_inputs/`](wells/source_inputs/) | Original survey declaration, well tracks, depth-time models and markers |
| [`wells/converted/`](wells/converted/) | Import-ready workbooks, CSV/VTK exports and validation results |
| [`scripts/`](scripts/) | Well conversion and dataset validation |
| [`metadata/`](metadata/) | Checksums, entity catalogue, dataset summary and provenance |
| [`docs/`](docs/) | Coordinate definitions and reproduction instructions |

XY coordinates are in metres in **ED50 / UTM zone 31N (EPSG:23031)**.
Z is **negative two-way travel time in milliseconds**. Physical measured
depth is stored separately for wells. See [coordinate definitions](docs/coordinates.md).

## Reproduce the well conversion

Use Python 3.11:

```bash
python -m pip install -r requirements.txt
python scripts/convert_wells.py
python scripts/validate_wells.py
```

Outputs are written to `results/wells/`. To verify the supplied project and
its geometry, run `python scripts/verify_dataset.py --geometry`.
See [reproduction and validation](docs/reproducibility.md) for details.

## Acknowledgements and licence

Original F3 seismic data were provided by NAM through NLOG. We thank
**dGB Earth Sciences** for making the F3 data available as an OpendTect project
through [TerraNubis](https://terranubis.com/datainfo/F3-Demo-2023).

F3 source data and bundled adaptations are provided under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Retain credit,
the licence and notices of modifications when sharing these data. The existing
repository CC0 licence applies to repository-original code and documentation;
it does not replace the F3 data licence. See [third-party notices](THIRD_PARTY_NOTICES.md).
