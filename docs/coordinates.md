# Coordinate definitions and well conversion

| Quantity | Convention |
| --- | --- |
| Horizontal CRS | EPSG:23031, ED50 / UTM zone 31N |
| X, Y | Metres |
| Vertical domain | Two-way travel time (TWT) |
| Z | `Z = -TWT_ms = -1000 × TWT_seconds` |
| Seismic sampling | 462 samples at 4 ms; the exact SEG-Y used here starts at 4 ms |
| Time-to-depth conversion | None |

Legacy raw-XY and stretched sample-index coordinates were corrected before
final9 was saved. They are not the current units. Do not divide current
coordinates again by 100 or 125. Archived arrays and transform descriptions
in field data describe provenance.

Meshes use the same XY/TWT frame. A numerical tetrahedron volume therefore has
mixed units (m²·ms), not cubic metres. Physical rock volume requires a justified
depth conversion.

## Well method

For original measured depth `d`, bracket supplied `.wlt` rows `(d0,t0)` and
`(d1,t1)`:

```text
t_seconds(d) = t0 + (d - d0) × (t1 - t0) / (d1 - d0)
Z(d) = -1000 × t_seconds(d)
```

X, Y and source track depth are independently interpolated from `.well`
stations using measured depth. No XY rescaling or reprojection is needed.
The original model time datum is retained; no extra 4 ms seismic-origin offset
is added. Negative model times above its datum produce positive Z and remain
in the converted trajectory.

Sampling includes every model knot, track station, marker depth, coverage
endpoint and additional stations spaced by at most 5 m measured depth.
Markers are explicit trajectory stations; equal-time intervals are preserved.
No extrapolation beyond common track/model coverage is allowed.

| Well | Converted end MD (m) | Stations | Markers |
| --- | ---: | ---: | ---: |
| F02-1 | 1424.099976 | 6172 | 18 |
| F03-2 | 2139.60 | 12271 | 18 |
| F03-4 | 1858.20 | 8255 | 18 |
| F06-1 | 1699.99 | 7258 | 18 |

Original measured depth and track depth remain separate attributes. The PZero
workbook importer's generic MD is calculated from mixed metre/time geometry;
it places markers and is not physical measured depth. Physical measured depth
is stored as `ORIGINAL_MD_m`.
