# final9 PZero project

Open `final9.p0` in PZero. Its companion `final9_p0` directory must stay beside
it. The selected revision is `rev_2026-10-19-11-34-25-e2409f9b`.

The pointer and all 220 revision files were copied byte-for-byte from the
supplied project. UUID filenames, collection tables, geometry, attributes and
saved provenance were retained.

| Collection | Entities |
| --- | ---: |
| Geological | 192: 49 polylines, 71 triangulated surfaces, 72 marker vertex sets |
| Meshes | 8 tetrahedral meshes |
| Wells | 4 trajectories |
| Boundary | 1 surface |
| Images/seismic | 0 |

The full volume is `TetraMesh_PyMeshIt`; seven separate material meshes are
also included. Map UUID files to readable names using the
[entity catalogue](../metadata/entity_catalog.csv).

The saved image collection is empty. The [main README](../README.md#open-the-project)
provides the Google Drive seismic link and a command to load it in a working
copy with its original UID. Do not rescale the saved interpretations.

Embedded VTK provenance may contain historical local source paths. These are
retained evidence in the byte-identical project, not required locations on a
new computer. Bundled geometry opens without those paths.
