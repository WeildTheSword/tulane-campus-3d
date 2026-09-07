# HANDOFF.md — Tulane Campus 3D

Living resume packet. Update in place; don't recreate.

## Goal & current task

**Goal:** a to-scale 3D model of Tulane's uptown campus for an open-world game, built only from public survey data and
public photos. Geometry from USGS 2021 QL1 LiDAR + OSM/city footprints; colour from a 2025 0.15 m orthophoto; building
exteriors from CC-licensed photos; a walkable path network with a navigation graph.

**Task in flight:** none. Everything is built, committed and pushed (`31869ac`), and the local page was opened on the user's
desktop. The next substantive work is scaling the facade pass from 1 building to the other 92 — see Ordered next steps.

**Scale of the modelled space** (computed 2026-09-07, geodesic): full build 1.64 × 1.88 km = **3.09 km²**, perimeter
7.05 km, diagonal 2.5 km. Campus core 1.01 × 1.49 km = 1.51 km². Walkable network 68.9 km (17.3 km pedestrian-only);
corner to corner on foot ≈ 30 min at 1.4 m/s.

## Status

- **DONE — geometry.** Full extent: 4,089 buildings (3,888 OSM − 13 demolished + 201 city + 13 scan-found), median interior
  residual **0.19 m**, inlier 0.976, 95% planar roofs, 12,000 trees. `eval_fit.py` prints this.
- **DONE — paths (2026-09-07).** 569 ways, 77.7 km (17.3 km on foot), nav graph 1,988 nodes / 2,447 edges; campus core is
  98% one connected component. `out/tulane_paths.glb` + `out/tulane_paths.json`.
- **DONE — facades, 1 of 93 buildings.** Howard-Tilton: judged two-pass spec `data/facades/howard_tilton.json`, plus a
  deterministic reproduction via `facade_extract.py` scored against it — wall **dE 3.8**, window pitch **2%**, storey height
  2%, glass **misses (dE ~12)**. 23 s/building, $0, no API.
- **DONE — data.** `data/naip*.png` + `data/ortho2025*.png` (5633×6427, EPSG:26915, RGB + NIR), `data/lidar/` six 2021 tiles,
  `data/osm.geojson`, `data/city_footprints.geojson`, `data/photos/howard_tilton/` (26 CC images + sidecars + ATTRIBUTION.md).
- **DONE — published page** https://claude.ai/code/artifact/824d3d3c-18a0-4195-b09d-51a819786498 (12.3 MB; toggles Paths,
  Facade, Fit, Trees, Names, Photo). Local copy `out/tulane_scan.html`.
- **DONE — git.** `main` = `31869ac`, pushed to `github.com/WeildTheSword/tulane-campus-3d`, tree clean.
- **NOT DONE —** facade specs for the other 92 named buildings (blocked on the name→Commons alias table); exact-polygon
  walls; roof-colour relief displacement; glass colour.

## Decisions + WHY

1. **`--bbox=` must use the `=` form.** argparse reads a bare `-90...` as a flag. Without `--bbox` the builder falls back to
   the OSM file's extent (7 × 5.7 km) and OOMs at 0.5 m on 16 GB.
2. **Only the 2021 GreaterNewOrleans LiDAR.** `build_model.py` reads *every* `.laz` in `data/lidar/`, so a stray 2002/2017
   tile silently contaminates the DSM. It is already QL1 (14.8 pts/m²) — `Docs/lidar-sources.md` proves nothing better exists.
3. **Canopy is inferred, not classified.** The 2021 scan has no vegetation/building classes (82.6% class 1). Roof evidence =
   single-return cells with multi-return share < 0.3 **and** NDVI below a per-image Otsu threshold (`build_model.py:302-311`).
4. **Roof planes fit to per-cell *mean* z, not max** (`build_model.py:395,423`) — max sits up-slope of the cell centre, and
   Gibson Hall fitted 0 planes with it.
5. **Ceiling at the measured max, not the p97 ridge** (`build_model.py:471`, tag `height:max`) — the ridge clip flattened
   Holy Name's steeple from 49 m to 30.7 m.
6. **Orthophoto tiles requested in UTM on an exact grid** (`fetch_naip.py:9`). Requesting in lon/lat makes ArcGIS pad the
   latitude span by 7.7%, duplicating a strip of ground at every mosaic seam (the user spotted it). The fetcher verifies the
   returned extent with `f=json` before downloading and writes `bbox_utm`; `build_model.py:190-213` samples by it.
7. **Cap-then-strip decimation** (`pack_web.py:95-124`) — plain quadric decimation collapsed wall bottoms into the roof edge,
   destroying ~95% of vertical wall area. Welding + a floor cap keeps 651/652 wall faces on Howard-Tilton.
8. **Facade colour is measured in code, not guessed by a model.** The model's role was choosing *where* to sample.
   `facade_extract.py:160-175` replaces that with white-patch exposure normalisation + consensus clustering: 13 of 23 photos
   agreed and outvoted a sunset shot, a night shot and a mis-masked frame, with no semantic triage.
9. **Exposure normalisation applies to opaque surfaces only** (`facade_extract.py:161,191`) — it estimates diffuse albedo,
   which is meaningless for specular glass whose colour is reflected sky.
10. **Photos are committed.** CC BY / BY-SA permit redistribution with attribution; every image has a sidecar and
    `data/photos/ATTRIBUTION.md` is generated from them. (An earlier framing implied a licensing constraint — there isn't one;
    the real reason had only ever been size.)
11. **Google Street View is excluded** — no key, and Maps Platform terms forbid caching, storing and "geodata extraction",
    which rules out baking derived geometry/textures into a game. Mapillary (CC BY-SA) is the substitute.
12. **`out/` stays untracked** — 3.4 GB, regenerates from the pipeline. Git LFS if it must ever be versioned.

## Ordered next steps

1. **Scale the facade pass.** Build the name→Commons-category alias table for the 93 named buildings (48 per-building
   categories exist under `Category:Tulane University Uptown Campus buildings`). A naive fuzzy match hit 40/93 and got two
   wrong (Howard-Tilton → "Tilton Hall"). **Untested idea that would make this mechanical:** Commons files carry GPS
   coordinates — verify each candidate by testing whether its photos fall inside that building's footprint from
   `out/tulane_enriched.geojson`. Then run `facade_extract.py` per building and drop the JSON into `data/facades/`;
   the packer and builder pick it up with no code change.
2. **Fix glass colour** — the one field deterministic code misses. Sample at the detected window-grid centres (pitch is
   already recovered to 2%) rather than thresholding the dark mode. Fall back to a vision pass only if that fails.
3. **Exact-polygon walls** (`Docs/accuracy-plan.md` §4 item 2) — walls are still 0.5–1 m grid staircases; extrude the
   OSM/city polygon and cap with the fitted planes. This also enables per-face window patterns (the spec knows Freret has
   slit windows; the shader currently applies one rhythm to all four faces).
4. **Path widths under canopy** — 105 ways fall back to typology defaults because the orthophoto sees crown, not paving.
   LiDAR return intensity distinguishes paved from grass and would recover them; intensity is not currently read.
5. **Roof-colour relief displacement** — ortho roof pixels are displaced by building lean; sample after shifting by
   height × look-angle.

## Files with line refs

- `build_model.py:47-50` `--no-paths`, `--path-width-from-ortho`, `--extra-footprints`. `:186` per-image Otsu `T_VEG`.
  `:190-213` `ortho_frac` / `ortho_px` / `sample_ndvi` / `sample_naip` / `uv_naip` (UTM-referenced ortho sampling).
  `:302-311` `has_veg` / `VEG_MIN` / `single` / `DSM1` / `M1` / `CANOPY` / `NDVI`. `:373-385` `FACADES`, `wall_rgb`,
  `color_vertices`. `:395` `fit_roof_planes` (sequential RANSAC). `:423` `reconstruct_roof`. `:471` `height:max`.
  `:509-517` `scan:absent` / demolished / post-scan logic. `:597` orphan log.
  **`:631-735` the path network** — `PED_TYPES:634`, `DEFAULT_W:635`, `grid_at:641`, `paved_width:646`, ribbon build from
  `:680`, `pz` at `:701` (**see Gotchas**), summary log at `:733`.
- `pack_web.py:30-32` `--decimate`, `--decimate-named`, `--facades`. `:95` `merge_by_position`, `:104` `floor_cap`,
  `:113` `decimate`, `:126` `dominant_angle` (facade frame `phi`), `:137` `load_facades`. `:196-199` path GLB packing.
  `:225` `__PATHS_B64__`, `:229` `__FACADES_JSON__`.
- `viewer/scan_template.html:83,85` Paths / Facade buttons. `:98` `glb-paths` slot, `:102` `facades-json` slot.
  `:163` `FACADE_GLSL`, `:190` `facadeMaterial`, `:204` `setFacades`, `:210` `addFitColors`, `:224` `addPaths`,
  `:276-277` button handlers, `:297-298` path load in the boot sequence.
- `facade_extract.py:49` `lidar_ruler` (height/levels = the metric ruler), `:65` `masks`, `:78` `building_mask`,
  `:91` `openness_periods` (autocorrelation rhythm), `:106` `analyse`, `:156` `REF_L`, `:160-175` `wmed` (consensus),
  `:191,197` glass with `normalise=False`.
- `fetch_naip.py:16-18` `--bands`, `--service`, `--license`; `:9` the UTM / `bbox_utm` rationale. `fetch_footprints.py` —
  city layer. `eval_fit.py:10` landmark list, `:13` loader.
- Docs: `Docs/lidar-sources.md` (no better LiDAR exists; verified sources), `Docs/accuracy-plan.md` (external validation,
  fixes, open items, §2b paths), `Docs/facade-method.md` (facade method + Howard-Tilton PoC).

## Gotchas / constraints

- **Never bind `x`, `y`, `z`, `c`, `m` at module level after line ~300.** They hold the LiDAR cloud and are still needed by
  the scan-surface export at the end of the file. Binding `z` in the path code silently broke that export
  (`IndexError: size of axis is 21`). Path locals are now `pz` / `npts` / `tang` / `pm` (`build_model.py:701` carries the
  warning comment). AST audit that catches it: walk `ast.Assign` / `For` / `AugAssign` targets for those names with
  `lineno > 500`.
- **`--bbox=` with the equals sign**, or argparse errors.
- **Use `.venv/bin/python`** — system `python3` is miniconda without the deps.
- **Overpass needs a User-Agent** (406 without). ArcGIS ImageServer: 4000 px per request, and content-type is not a success
  signal — check the PNG magic bytes.
- **Artifact page cap is 16 MB** and base64 adds 33%; the page is at 12.3 MB. three.js r128 from cdnjs; GLTFLoader and
  OrbitControls from `cdn.jsdelivr.net/npm/three@0.128.0/examples/js/...` (cdnjs 404s for the examples path).
- **GLTFLoader fetches a `blob:` URL for an embedded texture**, which the artifact sandbox blocks ("Load failed" on Safari).
  The orthophoto therefore ships as a `data:` `<img>` the page hands to three.js.
- **GLTFLoader sanitizes node names** (spaces → underscores) — building labels travel in node `extras`, not names.
- **NDVI is validated:** trees vs roofs separate at 88% (NAIP) / 86% (2025 ortho). A 9-polygon grass check once suggested it
  was broken; that sample was too small to conclude from. `bandIds=3` returns true NIR (bit-identical to the raw 4-band TIFF).
- **`ANTHROPIC_API_KEY` in this environment returns 401** — the batch facade path is untested; agent-driven passes work.
- Harness blocks `sleep` polling loops; use background tasks + notifications.
- Delegating a bounded task to a subagent costs ~5–15× less than doing it in a long session (context dominates); measured
  ~$0.13 (Opus subagent) vs ~$0.55–0.85 in-session.

## Open questions

- Do Commons files for these buildings carry GPS coordinates, and for how many of the 48 categories? This decides whether the
  alias table is mechanical or manual. **Untested.**
- Can glass colour be recovered deterministically by sampling at the recovered window-grid phase, or does it genuinely need a
  vision pass? Both thresholds tried miss in opposite directions (dE 10.8 too dark, dE 11.9 too light).
- Storey heights are the weakest attribute in the Howard-Tilton spec (confidence 0.55). Is there a deterministic route, or
  does it need the facade rectified first?
- OSM maps **no** `highway=steps` in this bbox, so the nav graph has no stairs. Real absence, or an OSM gap? Affects
  walkability realism.
- Should `out/` be tracked with Git LFS (3.4 GB) or stay regenerable? Currently regenerable.
- The user said the repo "is going to be private momentarily" — nothing built depends on it, but `ATTRIBUTION.md` was written
  assuming it might be public.

## Resume & verify

```bash
cd /Users/mweild/Downloads/tulane-campus-3d

# state of the built model
.venv/bin/python eval_fit.py out          # expect: 3857 measured, rmse median 0.19, inlier 0.976, 95% planar
grep -E "paths:|roof fit|done " out/build.log | tail -3

# rebuild (full extent, ~9 min)
.venv/bin/python build_model.py --bbox=-90.1290,29.9330,-90.1120,29.9500 --align-st-charles --surface \
  --res 0.5 --terrain-res 1.0 --surface-res 1.0 --obj --max-trees 12000 --naip data/ortho2025.png

# rebuild the campus core used by the page (~2 min), then repack
.venv/bin/python build_model.py --bbox=-90.1245,29.9332,-90.1140,29.9466 --align-st-charles \
  --res 1.0 --terrain-res 8.0 --out out/core_v2 --max-trees 4000 --naip data/ortho2025.png
.venv/bin/python pack_web.py --fine out/core_v2 --naip data/ortho2025.png \
  --out /private/tmp/claude-501/-Users-mweild-Downloads-tulane-campus-3d/bf6ae26f-83de-4d3c-9995-338036d4c447/scratchpad/tulane-scan.html

# facade extraction for one building (deterministic, no API, ~23 s)
.venv/bin/python facade_extract.py --photos data/photos/howard_tilton --name "Howard Tilton Memorial Library" \
  --out data/facades/howard_tilton.auto.json --compare data/facades/howard_tilton.json
# expect: wall dE ~3.8 match, window pitch 2% match, glass MISS
```

**Republish the page:** Artifact tool with the scratchpad path above — the same file path keeps the URL
`https://claude.ai/code/artifact/824d3d3c-18a0-4195-b09d-51a819786498`; from another session pass that URL as `url`.

**Branch/remote:** `main` at `31869ac`, in sync with `origin` (`github.com/WeildTheSword/tulane-campus-3d`). No PR. The
merged `lidar-accuracy-upgrade` branch can be deleted (`git branch -d lidar-accuracy-upgrade`).
