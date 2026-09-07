# Tulane Campus 3D

A to-scale 3D model of Tulane University's uptown campus for an open-world game, built from public survey data:

- **OpenStreetMap** building footprints, names, streets and the St. Charles streetcar line (ODbL — credit "© OpenStreetMap contributors")
- **USGS 3DEP LiDAR** — the airborne laser scan of New Orleans — for measured building heights, roof shapes, ground and trees (public domain)
- **USDA NAIP** aerial imagery for the ground texture and roof colors (public domain)

Plus a Crossy-Road-style **voxel viewer** (`viewer/tulane_voxel_campus.html`) that renders either its built-in reference layout or the real footprints, and exports OBJ for game engines.

## Get the model — three ways

1. **GitHub Actions (no setup)** — Actions tab → *Build campus model* → *Run workflow*. When it finishes (15–40 min), download the `tulane-campus-model` artifact.
2. **Google Colab** — open `notebooks/tulane_scan_colab.ipynb` in Colab (`File → Upload notebook`, or the Colab GitHub opener), then *Runtime → Run all*. Results are saved to Google Drive.
3. **Locally / Codespaces** — Python 3.10+:
   ```bash
   pip install -r requirements.txt
   python fetch_osm.py && python fetch_footprints.py    # OSM + the city's quarterly footprint layer
   python fetch_naip.py && python fetch_naip.py --bands 3 --out data/naip_nir.png   # NAIP colour + near-infrared (NDVI)
   # newer/sharper: LaDOTD 2025 6-inch 4-band ortho (see Docs/lidar-sources.md)
   # python fetch_naip.py --service https://maps.dotd.la.gov/imagery/rest/services/Imagery/2025_LouisianaCities_6IN_RGBI/ImageServer/exportImage --bands 0,1,2 --out data/ortho2025.png
   python fetch_lidar.py --list        # see which scans cover the campus
   python fetch_lidar.py --yes         # download the newest project only (~510 MB for the 2021 Greater New Orleans scan)
   python build_model.py --bbox=-90.1290,29.9330,-90.1120,29.9500 --align-st-charles --surface --res 0.5 --obj
   ```
   Pass `--bbox=` with the `=` (argparse otherwise reads the leading `-90` as a flag). Without `--bbox` the builder uses the
   OSM file's own extent, which is much larger than the campus and will run out of memory at fine resolutions.

### Phone-sized scan page

`pack_web.py` squeezes a build into one self-contained HTML page (`viewer/scan_template.html` + embedded GLBs, ≈12 MB) that
renders the laser-measured buildings, the orthophoto ground and the detected trees in three.js:

```bash
python build_model.py --bbox=-90.1245,29.9332,-90.1140,29.9466 --align-st-charles --res 1.0 --terrain-res 8 --out out/core   # campus core, fine roofs
python build_model.py --bbox=-90.1245,29.9332,-90.1140,29.9466 --align-st-charles --res 3.0 --terrain-res 8 --out out/core3  # same box, coarse roofs for houses
python pack_web.py --fine out/core --coarse out/core3 --out out/tulane_scan.html
```

Named campus buildings come from the fine build, unnamed houses from the coarse one (merged into a few meshes), positions are
int16-quantized (`KHR_mesh_quantization`, 5 cm) and the orthophoto is cropped to a JPEG.

## Outputs (`out/`)

| File | Contents |
|---|---|
| `tulane_buildings.glb` / `.obj` | one named mesh per building, walls at laser-measured height, roof surface from the scan |
| `tulane_terrain.glb` | ground surface from LiDAR ground returns, textured with the orthophoto |
| `tulane_trees.glb` + `.json` | tree instances detected from the canopy (position, height, crown radius) |
| `tulane_scan_surface.glb` | the raw scanned surface as one textured mesh |
| `tulane_enriched.geojson` | footprints with measured `height` — load it in the voxel viewer (Data → load) |
| `preview_dsm.png`, `model_stats.json` | sanity check and counts |

Units are meters, Y up; `--align-st-charles` puts St. Charles Avenue along +X so the viewer and the models share a frame.

## Engine import

- **Godot 4**: drop the `.glb` files into the project.
- **Unity**: glTFast package, or go through Blender.
- **Unreal**: File → Import (glTF), or Blender → FBX.
- Each building node carries its OSM name, so doors, colliders and quest triggers can be scripted per building.

## Walkways, roads and the navigation graph

`build_model.py` also builds the campus path network (disable with `--no-paths`):

- OSM centrelines (footway, path, steps, cycleway, pedestrian, plus roads) are clipped to the bbox, resampled at 2 m and
  **draped on the LiDAR ground surface**, so paths follow real grade instead of cutting through it.
- Width is **measured from the orthophoto** where it can see the paving edge: a probe walks out along the path normal until
  NDVI says vegetation. Where the path runs under tree canopy the probe refuses and the typology default is used — on this
  campus that is most walkways, and the build log reports the three cases separately.
- `out/tulane_paths.glb` holds ribbons grouped by surface; `out/tulane_paths.json` is a navigation graph
  (nodes with local x/y/z and lon/lat, edges with length, type, width, surface, rise, and `foot`/`steps` flags) an engine
  can path-find on directly.

NDVI is validated against LiDAR-detected trees vs building roofs: it separates canopy from roof at 88% (NAIP) / 86% (2025 ortho).

## Facades from public photos

`Docs/facade-method.md` describes the per-building method (name/Wikidata → Wikimedia Commons; address/coords → street imagery;
vision extraction with measured colours) and its proof on Howard-Tilton Memorial Library. A spec lives in `data/facades/<slug>.json`;
its `render` block drives two things:

- the page: `pack_web.py` ships each named building's facade frame (`phi`, `base`) and the spec, and `viewer/scan_template.html`
  paints walls procedurally in the fragment shader (storeys, piers, window cells, storefront, terrace, crown) — toggle **Facade**;
- the engine GLB: `build_model.py` gives walls private top vertices and paints them with the spec's wall colour.

`pack_web.py` decimates with a floor cap so walls stay vertical (plain quadric decimation collapsed them into the roof).

## Making it more photoreal

- Stream Google's Photorealistic 3D Tiles with Cesium for Unity/Unreal for live photogrammetry (API key + attribution; can't be baked into a build).
- Scan hero buildings on site with Polycam / Scaniverse / RealityScan and swap them in.

## Accuracy notes

Roofs are reconstructed from the scan per footprint (`build_model.py`, `reconstruct_roof`):

1. **Evidence cells** are 0.5 m (or `--res`) cells whose points are single-return and whose multi-return share is
   below 30 % — canopy never counts as roof, even where a dense crown returns single pulses.
2. **Roof planes** are fitted to the per-cell mean height by sequential RANSAC (tolerance `--plane-tol` + 0.25 × res,
   walls rejected by slope) and extended over cells hidden by trees or rooftop clutter; cells the planes clearly don't
   explain keep their measured height. 85–90 % of buildings end up planar.
3. **Fit metrics** are written to `tulane_enriched.geojson` for every measured building: `fit:rmse`, `fit:p90`,
   `fit:inlier` (share of interior cells within tolerance), `fit:cover` (share of the footprint with clean evidence),
   `roof:planes`, and `fit:rmse_raw` (what the previous all-returns method would have scored). `eval_fit.py` prints a
   summary and a landmark table; `pack_web.py` bakes the metric into the page's **Fit** heatmap.
4. Buildings the crown hides (`fit:cover` < 15 %) fall back to OSM `height`/`building:levels` or a typology estimate and
   are marked `height:source = estimate` (or `lidar-canopy` when at least 8 clean cells exist).
5. **Unmapped structures** — anything ≥ 2.5 m above ground, non-canopy, outside every footprint and off road corridors,
   ≥ `--orphan-min-area` m² — are polygonised from the scan and added as `source = lidar-unmapped` buildings.
6. **Tree crowns** come from a watershed of the canopy model seeded at the detected peaks (radius from crown area).
7. **Footprints** are OSM plus the City of New Orleans layer (`--extra-footprints`): city buildings OSM lacks are added; an OSM
   building the scan cannot see is dropped as demolished unless the city layer still has it, in which case it is a post-2021
   estimated block (`scan:absent`). `height` is the 97th-percentile ridge; `height:max` keeps steeples and penthouses.
8. **External checks** (Docs/accuracy-plan.md): footprints and orthophoto register to the scan within one cell; heights agree
   with FEMA USA Structures to a 0.6 m spread (+1.9 m convention offset). Docs/lidar-sources.md records why no better LiDAR exists.

On the campus core (1 m cells) the mean interior residual is ≈0.28 m with 97 % of cells within tolerance, versus ≈0.75–1.5 m
for the previous method. The NAIP imagery the USGS service holds for this area was flown May 2023; the scan is 2021.


Footprints are survey-grade; heights and roofs are measured from the scan (typically ±0.3 m). The 2021 Greater New Orleans
scan classifies only ground and noise, so trees are detected from multi-return pulse density rather than vegetation classes,
and canopy peaks above 32 m are discarded (cranes and towers absent from OSM). Buildings newer than the scan flight (check the project date in `fetch_lidar.py --list`) fall back to OSM tags or estimates and are flagged with `height:source` in `tulane_enriched.geojson`. Missing or outdated outlines are best fixed at openstreetmap.org, then re-run `fetch_osm.py`.
