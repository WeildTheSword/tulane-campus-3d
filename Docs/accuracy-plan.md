# Accuracy plan — what limits the dataset and what was done about it

Status as of 2026-09-06 (late). Numbers are from `eval_fit.py` on the campus core (`out/core_v2`, 1 m cells) unless stated.
"Verified" means measured in this repo against the actual data, not reported from memory.

## 1. External validation (first time the dataset has been checked against anything independent)

| Check | Method | Result | Verdict |
|---|---|---|---|
| Footprint ↔ LiDAR registration **verified** | cross-correlate the OSM footprint raster with the scan's non-canopy "tall" mask (nDSM > 3 m, multi-return share < 0.3), 0.5 m grid, ±8 m search, tile w0777n3315 | best shift **0.00 m E, 0.00 m N**; IoU 0.59 unchanged by any shift | no systematic offset; the 0.59 IoU is footprint imprecision + canopy, not misregistration |
| Orthophoto ↔ LiDAR registration **verified** | same, on gradient-magnitude maps (NAIP luminance vs DSM) | best shift 0.0 m E, **+0.5 m N**, correlation gain ×1.001 | within one cell → noise |
| Heights vs FEMA/ORNL USA Structures **verified** | 3,199 structures in bbox, 2,989 matched by centroid to our buildings | ours − FEMA: **median +1.90 m, MAD 0.60 m** (n = 2,978 LiDAR-measured); named outliers are towers/steeples FEMA averages away | tight agreement with a convention offset: FEMA's 2012 NGA height is mean-like, ours is the 97th-percentile ridge |
| Footprint completeness vs City of New Orleans layer **verified** | 3,766 city footprints in bbox (quarterly, rows 2026-08) vs 3,888 OSM | **201 city buildings absent from OSM** (largest 4,483 m²), **120 OSM buildings absent from the city layer** | adopted: city footprints merged, the scan adjudicates the 120 |
| Tulane facilities CAD footprints | ArcGIS `Tulane/FeatureServer` layer 11 | only 7 polygons in bbox, no heights | not useful |
| Better LiDAR | six-lane sweep, see `Docs/lidar-sources.md` | none exists; the 2021 scan is already QL1 | invest in reconstruction, not acquisition |

## 2. Defects found and fixed (this session), with measured effect

| # | Defect | Evidence | Fix | Effect |
|---|---|---|---|---|
| 1 | Canopy over roofs counted as roof (heights up to 3 m high, lumpy roofs) | Gibson Hall eave 14.7 → 17.2 m once multi-return points excluded; Howard-Tilton p97 31.6 vs single-return 28.8 | roof evidence = single-return cells with multi-return share < 0.3 **and NDVI < 0.5** | previous-method mean residual 0.75 → 0.26 m |
| 2 | Roofs were gridded max-height (stair-stepped, no planes) | Gibson Hall 0 planes when fit to per-cell *max* z | sequential RANSAC on per-cell *mean* z, tol = 0.2 + 0.25·res, planes extended over hidden cells | 85–97% of roofs planar; inlier 0.986 |
| 3 | Eave clip flattened lower wings | Tilton Memorial residual 0.97 → 1.82 with the clip | floor at base + 2 m only | Tilton 0.36 m |
| 4 | **Ridge clip flattened towers/steeples** (< 3% of footprint) | Holy Name church: raw points to 49 m, model 30.7 m | ceiling = measured max + 0.5 m; new tag `height:max` | steeple retained (height:max 39.4) |
| 5 | Under-canopy roofs got the median of mixed ground/crown returns (2.5–4 m "houses") | 157 buildings at h ≈ 3 m | ≥ 8 clean cells → `lidar-canopy`, else OSM levels/typology → `estimate` | 240 estimate + 13 lidar-canopy on the core; none invented |
| 6 | 0 trees (scan has no vegetation classes) | class histogram: 82.6% unclassified, 14.9% ground, no 3/4/5/6 | vegetation from multi-return density ∪ NDVI; watershed crowns; 32 m cap (crane) | 4,000 core / 12,000 full trees, median 15.6 m |
| 7 | Structures OSM lacks were invisible; then over-detected (1,484 incl. bbox-corner overhang, canopy, slivers) | contact sheets of candidates over the orthophoto | bbox-constrained, canopy ratio < 0.12, NDVI < 0.25, planar or smooth, drop < 120 m² slivers within 4 m of a footprint, ≤ 40 m | 33 on the full extent, each a real 2021 object (stands, annexes, tents, sheds) |
| 8 | OSM incompleteness / staleness | 201 missing, 120 stale (city layer) | `--extra-footprints`: add missing (IoU < 0.2); OSM-only + scan-absent → **demolished** (dropped); city + scan-absent → **post-scan** estimated block | core: +144 buildings, 8 demolished, 32 post-2021 |
| 9 | Imagery vintage (NAIP May 2023) vs scan (Nov 2021) and today | LaDOTD 2025 6-inch RGBI service verified | `fetch_naip.py --service …` → `data/ortho2025.png` (+ NIR) | current-year roof colours; NDVI thresholds recalibrated (see §4) |
| 11 | **Orthophoto mosaic seams: a duplicated strip of ground at every tile boundary** (user-reported from the previews) | ArcGIS exportImage requested in lon/lat returns a latitude span 7.7 % larger than asked (2,154 rows requested → ≈166 extra rows) to keep its pixel aspect; UTM requests return the exact grid | `fetch_naip.py` requests EPSG:26915 tiles on an exact pixel grid, verifies the returned extent with `f=json` before downloading, and writes `bbox_utm`; `build_model.py` samples colours/UVs/NDVI by UTM extent | seamless mosaic; roof colours and NDVI no longer shifted by up to ~50 m near seams |
| 10 | Per-building trust was invisible | — | `fit:rmse`, `fit:p90`, `fit:inlier`, `fit:cover`, `roof:planes`, `fit:rmse_raw`, `height:max`, `scan:absent`; **Fit** heatmap in the page | every building carries its own accuracy |

Metric trajectory on the core (mean residual vs single-return evidence, interior cells): 1.48 → 0.93 → 0.41 → 0.28 → **0.26 m**;
inlier fraction 0.947 → 0.974 → **0.986**; buildings > 1 m off: 8% → 3% → **1%**.

Full extent, 0.5 m cells (`out/`, 2026-09-06 23:58): **4,089 buildings** = 3,888 OSM − 13 demolished + 201 city + 13 scan-found; 3,848 measured; median residual **0.19 m**, mean 0.24 m (previous method 0.66); inlier **0.976**; **95% planar** roofs; 2% > 1 m; 63 buildings the city has but the 2021 scan does not (post-2021, estimated blocks); 12,000 trees, tallest 31 m.

## 2b. Pathways (added 2026-09-07)

The campus walk network was already in the OSM download and unused by the 3D pipeline. It is now built and exported.

| Check | Result |
|---|---|
| Network topology (campus core) | 1,533 nodes, 1,738 edges, **98% in one connected component**; 372 junctions, 119 dead ends |
| Coverage | 341 ways / 39.0 km in the core, 13.0 km pedestrian-only |
| Width measured from the orthophoto | 157 ways measured, 68 refused (path under canopy), 116 typology default |
| Measured vs assumed footway width | median **2.8 m** where visible, against a 1.8 m typology default |
| Elevation draping | median grade change 0.03 m/edge, max 1.0 m — correct for flat New Orleans |
| Stairs | 0 — OSM maps no `highway=steps` in this bbox (a data gap, not a pipeline gap) |

**NDVI validation (corrects an earlier unverified claim).** NDVI was added for canopy masking without checking polarity. A first
check against 9 OSM grass polygons suggested it was near-noise; that sample was too small to conclude from. Re-tested against
2,241 LiDAR-detected trees vs 1,495 building roofs, it works: separation +0.352 (NAIP) and +0.402 (2025 ortho), with a best
split of T=+0.14 / +0.06 giving 88% / 86% canopy-vs-roof accuracy. `bandIds=3` was confirmed to return true NIR by comparing
against the raw 4-band TIFF (bit-identical NDVI).

**Known limit:** orthophoto width measurement cannot see a path under tree canopy — the same canopy problem that forced
multi-return filtering for roofs. LiDAR intensity (paved vs grass differs in return intensity) would recover those widths and
is the natural next step.

## 3. Refuted / not pursued

- **NAIP 2021 vintage to match the scan** — the USGS service holds only May 2023 for this area (queried); superseded by the 2025 LaDOTD ortho anyway.
- **Registration correction** — measured at zero (above); nothing to fix.
- **Overture / Microsoft heights as a source** — 3 m low vs LiDAR (eave-like), 9% within 1 m; useless next to a 0.26 m fit.
- **Better LiDAR** — none (see sources doc).
- **Façade geometry** — not obtainable from any airborne source; needs street-level photogrammetry.
- **Google Street View** — no API key present, and Maps Platform terms forbid pre-fetching, caching, storing and "geodata extraction", which excludes baking derived geometry or textures into a game asset. Mapillary (CC BY-SA) is the licensed substitute and already contributes photos to the Howard-Tilton facade spec.

## 4. Open items, in order

1. ~~NDVI calibration for the 2025 ortho~~ — done: thresholds are now relative to a per-image Otsu vegetation threshold (NAIP ≈ 0.2, LaDOTD 2025 lower), measured on canopy/turf/roof reference sites.
2. **Exact-polygon walls** — walls are still rasterised on the grid (stair-stepped footprint edges at 0.5–1 m). Extrude the OSM/city polygon exactly and cap it with the fitted planes; expected visible gain on every building edge, no change to height metrics.
3. **Roof colour displacement** — the orthophoto's roof pixels are relief-displaced relative to the footprint; sample colours after shifting by height × the ortho's look-angle, or use the 2025 true-ortho if the service exposes one.
4. **LaDOTD 0.5 m bare-earth DEM** as an independent terrain check (`Docs/lidar-sources.md` #4).
5. **Ground-truth heights from published sources** (NRHP forms, Tulane facilities) — the workflow lane hit the session limit; only the FEMA cross-check ran.
6. Re-run the failed workflow lanes after the usage window resets (11:30 pm Chicago): `Workflow({scriptPath: …, resumeFromRunId: 'wf_38394a7c-3aa'})` replays the 24 finished agents from cache.

Acceptance criteria for further work, in the existing metrics: mean interior residual ≤ 0.25 m, inlier ≥ 0.985, > 1 m share ≤ 1%, FEMA offset MAD ≤ 0.6 m, and no regression on the landmark table printed by `eval_fit.py`.
