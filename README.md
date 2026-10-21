# PZero F3 dataset
[![DOI](https://zenodo.org/badge/942090951.svg)](https://doi.org/10.5281/zenodo.21792099)


PZero and PyMeshIt project files and well-conversion scripts for the F3 North Sea dataset.
The final9 project includes geological interpretations, surfaces, four wells
with 72 markers, and tetrahedral meshes.

## Manuscript tutorial

Follow the [seven-step tutorial with screenshots](Tutorial/README.md) to open
the manuscript projects, reconnect the F3 seismic volume, and inspect the
interpretations, wells, reconstructed surfaces and saved tetrahedral mesh.

## Open the project

Open [`final9/final9.p0`](final9/final9.p0) in
[PZero](https://github.com/gecos-lab/PZero). Keep `final9_p0/` beside it.

**F3 seismic: [Download from Google Drive](https://drive.google.com/drive/folders/0B7brcf-eGK8CbGhBdmZoUnhiTWs?resourcekey=0-0ZhV_OJ3TKN1ShFAGcrOzQ).**

1. Download `Dutch Government_F3_entire_8bit seismic.segy`.
2. With the project open, use **File > Import SEGY** and select the file.
3. In **Link interpreted entities**, select the existing horizon/fault group
   and confirm. Save the project to retain the links.

## PyMeshIt project

Open [`PyMeshIt project/seis2_aligned.pmit`](PyMeshIt%20project/seis2_aligned.pmit)
in PyMeshIt.

## Wells

| Folder | Contents |
| --- | --- |
| [`wells/source_inputs/`](wells/source_inputs/) | Well tracks, depth-time models and markers |
| [`wells/converted/`](wells/converted/) | Converted workbooks and CSV/VTK files |
| [`scripts/`](scripts/) | Well conversion and validation scripts |

To import a converted well in PZero, use **File > Import Well Data** and select
its `*_pzero_well.xlsx` workbook from `wells/converted/`.

To run the conversion, use Python 3.11 from the repository root:

```bash
python -m pip install -r requirements.txt
python scripts/convert_wells.py
```

New outputs are written to `results/wells/`.
See [well instructions](wells/README.md) for input and output details.

## Acknowledgements and licence

F3 seismic data originate from NAM through NLOG. We thank **dGB Earth Sciences**
for making the F3 data available as an OpendTect project through
[TerraNubis](https://terranubis.com/datainfo/F3-Demo-2023).

F3 source data and adaptations, including the PZero interpretations, meshes
and converted wells, retain [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
Keep attribution, identify modifications and share adaptations under the same
licence. The repository's [CC0 licence](LICENSE) covers its original code and
documentation and does not replace the F3 data licence.
