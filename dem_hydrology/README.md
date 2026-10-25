# DEM Hydrology Toolkit (QGIS plugin)

One plugin that runs every hydrology analysis that can be derived from a DEM, with automatic
symbology, standard maps, an Excel summary and a PDF report. All analyses keep their original
names (Catchment Area, Strahler Order, HAND, TWI, ...) and each one lists its formula, limitations
and scientific references.

**Author:** Rizal Brilliant Nugraha - rizalb123@gmail.com
**Support the author:** https://sociabuzz.com/rizalb123
**License:** GNU GPL v2 or later

## Installation
1. In QGIS: Plugins > Manage and Install Plugins > Install from ZIP > choose `dem_hydrology.zip`
   (or install it from the official plugin repository once published).
2. numpy and scipy ship with QGIS. For the Excel summary make sure `openpyxl` is available; if not, open the
   OSGeo4W Shell (Windows) or a terminal and run `python -m pip install openpyxl`. Without openpyxl every other
   output is still produced and only the Excel file is skipped.
3. The plugin icon appears in the toolbar and in the Plugins menu.

## How to use
1. **Data** - pick the DEM (metre units), the study-area boundary (polygon) and an output folder. Optional:
   an administrative boundary layer plus label field (dotted lines and labels on the maps) and an outlet point
   layer (for point-based watersheds). A DEM in a geographic CRS is reprojected to UTM automatically.
2. **Analyses** - tick the analyses you want or choose a preset (watershed and stream, flood, erosion, recharge,
   surface morphology). Click an analysis to read its description, formula, limitations and references.
   Derived analyses compute their prerequisites automatically.
3. **Parameters** - every parameter is editable (stream threshold, sub-basin order, MFD exponent, Manning n,
   composite-index weights, water levels, ...). The last values are remembered.
4. **Output** - choose PNG maps, Excel, PDF and whether to load results into the QGIS project.
5. Press **Run analysis**. A pop-up summarises the run when it succeeds. The process can be cancelled.

## Languages
The language selector at the top of the dialog switches the interface, the logs, the maps, the Excel workbook
and the PDF report. English, Indonesian, Spanish, French and Portuguese are built in. The default follows the
QGIS interface language.

Add or change a language yourself:
1. Press **Export translation template** (it creates `my_language.json` in your language folder and opens it).
2. Translate the values (keep placeholders such as `%s`, `%d`, `%.1f` unchanged) and set `"_meta" > "name"`
   to the language name.
3. Rename the file to the language code, for example `de.json`, and select the language from the list.
   Files in the language folder override built-in languages with the same code. Missing texts fall back to English.

The language folder is `<QGIS profile>/dem_hydrology_languages/` (button **Language folder**).

## Output
- `results/` - GeoTIFF and GeoPackage files, styled when loaded into QGIS.
- `maps/` - one PNG map per output (grey background, white study area with a thick outline, dotted
  administrative boundaries with labels, north arrow, black-and-white scale bar, legend top right).
- `DEM_Hydrology_Summary.xlsx` - summary, parameters, statistics, class areas, streams per order, basin
  morphometry, order per basin, hypsometry, channel profile, time-area, sub-basins, point watersheds,
  depressions, inundation, index weights, methods and references.
- `DEM_Hydrology_Report.pdf` - all maps, tables, charts, morphometry, methods and references.

## Analyses (30)
1. Pre-processing: Fill Sinks (Priority-Flood), Sink / Depression Analysis
2. Terrain: Slope (+ Slope Class), Aspect, Hillshade, Curvature (profile and plan), TPI, TRI, Landform Classification
3. Flow: Flow Direction D8, Flow Accumulation / Catchment Area, D-Infinity (direction and SCA), MFD Catchment Area, Flow Path Length
4. Streams: Stream Network + Strahler Order + Shreve Magnitude
5. Watersheds: Sub-Watershed (order >= N), Watershed from Pour Points, Basin Morphometry and Hypsometry
6. Indices: TWI, SPI, STI, LS Factor (RUSLE), HAND (+ flow and straight-line distance to stream), Drainage Density, Time of Concentration / Isochrone (+ time-area)
7. Inundation: HAND Flood Inundation, Bathtub Inundation
8. Composite: Flood Susceptibility, Recharge Potential, Erosion Susceptibility (editable weights)

## Verification
- Slope, aspect and hillshade were compared with GDAL (Horn): slope difference < 0.002 %, aspect < 0.06 degrees.
- Depression filling was compared with an independent Planchon-Darboux implementation and yields a pit-free DEM.
- D8, D-Infinity and MFD accumulation conserve mass; D-Infinity angles match analytic values.
- Strahler order and Shreve magnitude match an independent recursive implementation on random trees.
- On a V-shaped valley DEM with hand-computable answers, area, perimeter, flow path, Rf, Re, Rc, relief,
  HAND and stream density match the theoretical values (difference <= 0.3 %).
- LS factor and STI match the published formulas.

## Limitations to keep in mind
- Everything is DEM-only. Composite indices are topographic and relative to the study area; they are not a
  hydraulic model or a soil-loss estimate. Default weights are equal; adjust and validate them with field data.
- Streams, watersheds and morphometry depend on the catchment-area threshold and the DEM resolution. Travel time
  and time of concentration use assumed velocities, so absolute values are indicative.
- A DSM (canopy and buildings) can divert flow; use a DTM when available.
- Watersheds touching the DEM edge are truncated; enlarge the buffer. The plugin warns about it.
- The analysis grid is capped (default 4 million cells); denser DEMs are resampled automatically.
