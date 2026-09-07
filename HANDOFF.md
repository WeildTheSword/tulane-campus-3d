# HANDOFF.md — Tulane Campus 3D

Living resume packet. Update in place; don't recreate.

## Goal & current task

**Goal:** Build a to-scale, photoreal-as-public-data-allows 3D model of Tulane's uptown campus (OSM footprints + USGS 3DEP 2021 LiDAR + NAIP 0.3 m orthophoto) and get it into the voxel viewer / game engines. User's ask (2026-09-06): "Do the whole thing. Use the most advanced scanning and method to map the campus and make the environment look exactly like Tulane's campus."

**Task in flight:** none. Path network built and published; full-extent build complete (4,089 buildings, 12,000 trees, 569 path ways / 2,447 graph edges). Everything since commit 3444e2c is uncommitted — offer to commit.

## Status

- DONE (2026-09-07) — **walkway/road network**: `build_model.py` clips OSM highway centrelines to the bbox, resamples at 2 m, drapes them on `DTM_fine`, measures width from the orthophoto (NDVI edge probe, refuses under canopy), and writes `tulane_paths.glb` (ribbons by surface) + `tulane_paths.json` (nav graph: nodes x/y/z/lon/lat, edges with m/type/width/surface/rise/foot/steps). Full extent: 569 ways, 77.7 km, 17.3 km on foot, 1,988 nodes / 2,447 edges; core graph 98% one connected component. Toggle **Paths** in the page. Disable with `--no-paths`.
- DONE — **facades from photos**: `Docs/facade-method.md`, `data/facades/howard_tilton.json` (judged), plus `facade_extract.py` — deterministic, no API: wall dE 3.8, window pitch 2%, glass misses (dE ~12). 23 s/building, $0.
- KNOWN LIMITS — orthophoto cannot measure path width under canopy (105 ways); OSM maps no `highway=steps` in the bbox; glass colour needs a vision pass.
- WATCH OUT — the paths code runs at module level where the LiDAR arrays `x,y,z,c,m` are live; binding `z` there broke the scan-surface export once. Names are now `pz/npts/tang/pm` with a comment; an AST audit script is in the session log if it recurs.

- DONE — facade method researched (25-agent workflow, all verified): `Docs/facade-method.md`; Howard-Tilton spec `data/facades/howard_tilton.json` (judged two-pass; wall #a8a49c precast, trim #5a4437, glass #383836, frames #2f2a25, 2014 addition crown) with photos + licences under `data/photos/howard_tilton/` (gitignored, re-fetchable).
- DONE — `pack_web.py`: cap-then-strip decimation (HT keeps 651/652 wall faces; page 11.48 MB), `phi/base/h` extras, `--facades`; `viewer/scan_template.html`: procedural facade shader + Facade button; `build_model.py`: private wall-top vertices, `wall_rgb()` from specs.
- DONE — research: `Docs/lidar-sources.md` (no better LiDAR exists; 2025 LaDOTD 0.15 m RGBI ortho + city footprints adopted). Workflow wf_38394a7c-3aa hit the session limit after 24/75 agents; its journal was salvaged by hand; audit lanes (ground-truth heights, code audit) never ran — see accuracy-plan §4.
- DONE — external validation: registration 0 m (footprints) / +0.5 m (ortho); FEMA USA Structures +1.9 m median offset, MAD 0.6 m; city layer: 201 missing / 120 stale OSM buildings.
- DONE — builder v4: single-return + canopy-ratio + NDVI(Otsu) evidence, RANSAC planes, tower-safe ceiling (`height:max`), city-footprint merge with demolished/post-scan logic, orphan filters, watershed crowns, UTM-referenced ortho sampling.
- DONE — fetcher: `fetch_naip.py` requests UTM tiles on an exact grid (the lon/lat request padded latitude by 7.7 % → duplicated seam strips, user-reported). `fetch_footprints.py` for the city layer. Data re-fetched: `data/naip*.png`, `data/ortho2025*.png` (5633×6427, EPSG:26915).
- DONE — core validated: median 0.25 m, inlier 0.986, 85% planar, 1% > 1 m; 11 scan-found structures, 8 demolished, 32 post-2021; page repacked and republished (12.1 MB) with the 2025 ortho credit.
- DONE — full-extent build: 4,089 buildings, median 0.19 m, inlier 0.976, 95% planar, 13 structures, 13 demolished, 63 post-2021, 12,000 trees; GLBs in `out/` regenerated with the 2025 ortho (terrain 278 MB).
- DONE — committed on `lidar-accuracy-upgrade` (5cf05bd); `.venv/` ignored. NOT DONE — merge to `main`; exact-polygon walls; roof colour displacement; published ground-truth heights.

## Decisions + WHY

0. **Accuracy method (2026-09-06 evening)** — evidence = single-return cells with multi-return share < 0.3 (single-return alone let dense crowns through: tail of 4 m residuals on houses); planes fit to per-cell *mean* z (max is biased up-slope; Gibson Hall got 0 planes with max); tol = plane_tol + 0.25·res; residuals on interior cells (edge ring mixes wall/ground); eave clip removed (flattened Tilton's lower wing); under-canopy → clean cells if ≥ 8 else OSM/typology estimate (median of mixed single returns gave 3 m houses); orphan cap 40 m. NAIP has no 2021 vintage here (only May 2023) → noted in stamp, not fixable.
1. **`--bbox=` explicit, with `=`** — see Gotchas; without it the OSM extent (7×5.7 km) OOMs at 0.5 m.
2. **Build flags for full res:** `--align-st-charles --surface --res 0.5 --terrain-res 1.0 --surface-res 1.0 --obj`. Max fidelity the script supports at ~14.5 pts/m².
3. **Only the 2021 GreaterNewOrleans project** — newest/densest; `build_model.py` reads every `.laz` in `data/lidar/` so older projects would contaminate.
4. **Tree detection uses multi-return density** (`build_model.py` `read_lidar` collects `number_of_returns>1`; `VEG` = count of those per 0.5 m cell, `VEG_MIN=2`) because the 2021 scan has no vegetation classes (82.6% class 1, 14.9% ground, rest noise). Original code produced 0 trees.
5. **Tree cap `chm < 32 m`** — 24 detections of 37–58 m clustered at one spot (~(200,−40) in the full frame) = a 2021 crane/tower not in OSM.
6. **Packer, not trimesh export, for the web page** — trimesh's GLB (float32 colors, normals, full 57 MB PNG) is 5–10× too big. `pack_web.py` writes int16 positions (KHR_mesh_quantization, 5 cm), uint8 colors, uint16 indices, no normals, JPEG crop of the orthophoto, names in node `extras` (GLTFLoader sanitizes node names, spaces→underscores).
7. **Houses at 3 m, named at 1 m** — 2 m houses gave a 15.0 MB page (too close to the 16 MB artifact cap for phones); 3 m gives 11.9 MB.
8. **NAIP tiled at native 0.3 m; Overpass with UA; LiDAR grouping by 5th title word** — fetcher bugs, all in Gotchas.

## Ordered next steps

1. Ask the user whether both artifacts render on their phone; if the scan page fails, open browser console — likely suspects listed under Status.
2. When bg task `bcdkrebj0` finishes: `tail -3 out/build.log`, confirm `trees` count and no error; `out/tulane_trees.json` max height should be < 32.
3. If the user wants engine files on the phone/other device: `out/*.glb` are 176–252 MB — too big for SendUserFile; suggest zipping `out/tulane_buildings.glb` + `tulane_trees.glb` + `tulane_enriched.geojson` (~180 MB) or building a `--res 1.0` variant.
4. Commit when asked: fetchers, `build_model.py`, `pack_web.py`, `viewer/scan_template.html`, README, HANDOFF (`.gitignore` already excludes `data/`, `out/`, `*.laz`; `.venv/` is NOT ignored — add it).
5. Optional polish on the scan page: label collision avoidance, a "Loyola" toggle, per-house picking (would need per-building meshes → bigger file).

## Files with line refs

- `build_model.py:32` `--bbox`; `:43` `--max-points`; `:44` `--max-trees`; `read_lidar` `:170-207` (multi-return flag collected at `:197`, returned `:207`); DSM/VEG grid `:247-262` (`has_veg`/`VEG_MIN` at `:255-258`); tree peaks `:400-411` (32 m cap at `:407`); enriched geojson `:467-469`.
- `pack_web.py:26-32` `is_named()`; `GLB` writer `:38-76` (quantization `:51-54`, extras `:63`); buildings `:86-103`; terrain+JPEG `:106-119`; trees/meta/template fill `:122-130`.
- `viewer/scan_template.html` — CSS/tokens top; markup `#app`; data slots `__BUILDINGS_B64__` etc.; JS: `b64ToBuf`, `parseGLB`, `addBuildings` (labels from `userData.label`), `addTerrain`, `addTrees` (InstancedMesh), `frameScene/reset/topView`, `pick`, dock handlers, `updateLabels`, boot IIFE at the end.
- `viewer/tulane_voxel_campus.html:545` `buildFromGeoJSON`; `:781` initial `load(buildReference)` — the scratchpad copy replaces this with `load(r=>buildFromGeoJSON(r, window.SURVEY))` and injects `<script id="survey-data">`.
- `fetch_osm.py:10-13`, `fetch_naip.py` (whole file), `fetch_lidar.py:13-15`.

## Gotchas / constraints

- **Never request ImageServer tiles in lon/lat** (bboxSR/imageSR 4326): the server pads the latitude span (+7.7 %) and the mosaic gets duplicated strips at seams (user spotted it). `fetch_naip.py` now uses EPSG:26915 with an exact grid + extent check; sidecar has `bbox_utm`, which `build_model.py` prefers.

- 16 GB RAM: full-res build peaks high; if OOM, `--max-points 30000000`.
- `python3` = miniconda without deps; use `.venv/bin/python`.
- argparse: `--bbox=-90...` (equals sign) or it errors "expected one argument".
- Overpass: UA header required (406 without); kumi mirror 429s.
- USGS NAIPPlus: 4000 px/request cap; check PNG magic, not content-type.
- Artifact CSP: three r128 from cdnjs; GLTFLoader/OrbitControls from `cdn.jsdelivr.net/npm/three@0.128.0/examples/js/...` (cdnjs 404s for examples). Fonts from Google Fonts only.
- Artifact page cap 16 MB; base64 adds 33%.
- Artifact viewer blocks page-initiated downloads (voxel viewer's export buttons are inert there).
- Harness blocks `sleep` chains; use background tasks + notifications.
- GLTFLoader sanitizes node names → use `extras`/`userData` for labels.

## Open questions

- Does the scan page actually render on iOS Safari (12 MB base64 decode + 1.4M-triangle scene with shadows)? Unverified. Fallback: lower `--tex`, drop shadows, or houses as flat boxes.
- Is the campus-core bbox right for the user (includes Loyola and surrounding blocks)? Chosen from named Tulane buildings ±80 m.
- Should `.venv/` be gitignored (currently not)?
- User's earlier "connect to Claude mobile" — unknown whether they restarted with `--remote-control`.

## Resume & verify

```bash
cd /Users/mweild/Downloads/tulane-campus-3d
tail -3 out/build.log                      # final full-res build: expect 'done {... trees: N ...}' with N ≤ 12000
.venv/bin/python -c "import json;t=json.load(open('out/tulane_trees.json'))['trees'];print(len(t),max(x['height'] for x in t))"   # max < 32
ls -la out/tulane_scan.html                # ≈ 12 MB
.venv/bin/python pack_web.py --fine out/core --coarse out/core3 --out out/tulane_scan.html   # rebuild the page (≈1 min)
```

Republish: Artifact tool with the scratchpad path `/private/tmp/claude-501/-Users-mweild-Downloads-tulane-campus-3d/bf6ae26f-83de-4d3c-9995-338036d4c447/scratchpad/tulane-scan.html` (or pass `url`). Branch `main`, no PR.
