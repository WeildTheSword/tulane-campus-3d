# Where to get roof LiDAR for the Tulane uptown campus

Bbox `-90.1290,29.9330 → -90.1120,29.9500` (UTM 15N). Compiled 2026-09-06 from a six-lane source sweep (USGS 3DEP/EPT, NOAA Digital
Coast, Louisiana state/LaDOTD, City of New Orleans/regional, OpenTopography/academic, commercial + derived heights). Items marked
**verified** were reproduced against the live endpoint by an independent skeptic (or by hand); everything else is as reported by the
finder and should be re-checked before relying on it.

## Verdict

**There is no better airborne LiDAR of this campus than the one already in `data/lidar/`.** Every lane converged on the same
acquisition: USGS 3DEP `LA_2021GreaterNewOrleans_C22`, work unit `LA_2021GNO_1_C22`, flown 2021-11-12 → 11-20 (Leica TerrainMapper,
Sanborn for LaDOTD), published 2023-06-21. It is a **QL1** collection (spec ≥ 8 pts/m²; the campus tiles measure 14.5–14.8 pts/m²
all-returns), LAS 1.4 PDRF 6, NAD83(2011)/UTM 15N + NAVD88 (Geoid18) metres. It carries only classes 1/2/7/9/17/18/20/21/22 — **no
vegetation (3/4/5) or building (6) classes** — which is why the pipeline derives canopy from multi-return share and NDVI instead.
No post-2021 3DEP work unit reaches the campus (WESM + 3DEP index queried), NOAA holds no newer coverage, and nothing academic
(NCALM, G-LiHT, NEON, OpenTopography's own collections) covers New Orleans.

The only ways to get *better* roof geometry than this scan are photogrammetric DSMs from commercial flyers (Vexcel Elevate ~7.5 cm,
Nearmap 3D) under commercial licences, or flying it yourself (drone LiDAR / photogrammetry with campus permission). Airborne LiDAR
of any kind cannot give façades.

## Sources, ranked for this project

| # | Source | Year | Density / GSD | Classes | Access | Licence | Value here |
|---|---|---|---|---|---|---|---|
| 1 | **USGS 3DEP `LA_2021GNO_1_C22` LAZ tiles** (current data) **verified** | 2021-11 | 14.5–14.8 pts/m² | 1,2,7,9,17,18,20–22 | `https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/LA_2021GreaterNewOrleans_C22/LA_2021GNO_1_C22/LAZ/` — `python fetch_lidar.py --yes` | public domain | the best there is |
| 2 | Same acquisition as **Entwine Point Tiles** **verified** | 2021 | identical (91.8 G pts project-wide, EPSG:3857) | identical | `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/LA_2021GNO_1_C22/ept.json` — PDAL `readers.ept` with a bounds filter (PDAL not in `.venv`) | public domain | convenience only: stream a bbox without 500 MB of tiles |
| 3 | Same acquisition via **NOAA Digital Coast DAV #9858** **verified** | 2021 | identical | identical (InPort 70255) | `https://coast.noaa.gov/dataviewer/#/lidar/search/where:ID=9858/details/9858` | public domain | AOI clipping / reprojection UI; not re-classified |
| 4 | **LaDOTD 2021 GNO 0.5 m bare-earth DEM** (OPR, hydro-flattened) **verified** | 2021 | 0.5 m raster, NVA 7.9 cm | ground only | `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/OPR/Projects/LA_2021GreaterNewOrleans_C22/LA_2021GNO_1_C22/TIF/` or ImageServer `https://maps.dotd.la.gov/imagery/rest/services/Elevation/2021_Greater_NewOrleans_1M_DEM/ImageServer` | public domain | independent ground surface to check `tulane_terrain.glb` / building bases (roofless) |
| 5 | **LaDOTD / NORPC 2025 Louisiana Cities 6-inch RGBI ortho** **verified by hand** (service metadata + export) | 2025 | 0.15 m, 4 bands (RGB + NIR), U8 | imagery | `https://maps.dotd.la.gov/imagery/rest/services/Imagery/2025_LouisianaCities_6IN_RGBI/ImageServer` — `python fetch_naip.py --service <url>/exportImage --bands 0,1,2 --out data/ortho2025.png` and `--bands 3 --out data/ortho2025_nir.png` | RESTRICTIONS=No per service; "Data Collected by NORPC" | **adopted**: current-year roof colours/textures, 2× NAIP resolution, NIR for NDVI, and change detection vs the 2021 scan |
| 6 | LaDOTD 2023 Various 6-inch RGB ortho **verified by hand** | 2023 | 0.13 m, 3 bands | imagery | `.../Imagery/2023_Various_6IN_RGBI/ImageServer` | as above | same year as NAIP, 2× finer; no NIR |
| 7 | NOAA NGS DSS 4-band 0.25 m mosaic, New Orleans, 2025-02-20 (DAV #10309) | 2025-02 | 0.25 m, RGBN | imagery | `https://coastalimagery.blob.core.windows.net/digitalcoast/NewOrleansLA_RGBN_2025_10309/` (tile index + url list) | public domain | winter capture (live oaks keep leaves, so little roof gain); ortho uses a 30 m DEM → building lean |
| 8 | City of New Orleans **Building Footprint** (quarterly) **verified by hand** | 2026-08 | vector | 2D polygons | `https://data.nola.gov/resource/prh5-qsuf.geojson?$where=within_box(the_geom,…)` — `python fetch_footprints.py` | public | **adopted**: 3,766 in bbox; 201 buildings OSM lacks, 120 OSM buildings the city no longer has |
| 9 | FEMA/ORNL **USA Structures** with HEIGHT **verified by hand** | footprints 2012/2019, heights NGA 2012 | vector | HEIGHT (m), OCC_CLS | `https://services.arcgis.com/VhMjCzR3cIjEkh7L/arcgis/rest/services/USA_Structures/FeatureServer/0` | public | external height cross-check: 2,978 matches, ours − theirs = +1.9 m median, MAD 0.6 m (convention offset: mean-like vs ridge) |
| 10 | Tulane facilities CAD footprints (`Tulane` FeatureServer, layers 2/11) | 2026-02 CAD | vector | 2D, Elevation=0 | `https://services2.arcgis.com/Ivj6zqXlq0qbCd1N/arcgis/rest/services/Tulane/FeatureServer` | unknown | layer 11 has only 7 polygons in bbox; layer 2 reported 117 (unverified) — not worth adopting |
| 11 | NGA HSIP New Orleans 3D Buildings 2012/2008 LOD1 (+ 3D trees) | 2008/2012 | LOD1 extrusions | height attr | `https://tiles.arcgis.com/tiles/QCty4ZXRXx9qyVVL/arcgis/rest/services/NGA_New_Orleans_3D_Buildings_2012_LOD1/SceneServer` | unknown | older, flat-top; I3S only |
| 12 | USGS/NOAA `LA_UpperDeltaPlain_2015` (flown 2017) **verified** | 2017 | 5.3 pts/m² | has class 3 low veg (+ ground) | rockyweb / NOAA DAV #8564 EPT `https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/8564/ept.json` | public domain | second epoch for change detection only |
| 13 | USACE HSDRRS 2012 (NOAA DAV #6350) **verified** | 2012-03 | 4.0 pts/m² | 1,2,7,9,12 | `.../entwine/geoid18/6350/ept.json` | public domain | third epoch only |
| 14 | `LA_STATEWIDE_2002` **verified (refuted as useful)** | 2002 | 0.1 pts/m² | — | rockyweb legacy | public domain | obsolete |

### Commercial / derived (none adopted)

- **Vexcel** Elevate DSM (7.5 cm photogrammetric, ~178 samples/m², urban refreshes 2021–2026; Bluesky Urban ortho over New Orleans Mar–Apr 2024 and 2025) — the only candidate that would be *denser and newer* than the scan; no published vertical accuracy, unclassified, commercial licence; the University Access Program forbids vectorised derivatives.
- **Nearmap 3D** (44 pts/m² photogrammetric, 37.8 cm RMSEz) — campus coverage unverifiable without an account; enterprise pricing.
- **Hexagon HxGN** DSM (20–30 cm, RMSEz 40–60 cm) — no better than the scan; Metro HD LiDAR city list excludes New Orleans.
- **Google Photorealistic 3D Tiles** — cannot be exported, cached or baked (Map Tiles API policy); streaming-only with attribution.
- **Esri 3D Buildings / Mapbox / Cesium OSM Buildings** — licences forbid extraction; heights are OSM-level guesses anyway.
- **Overture / Microsoft ML footprints with height** (release 2026-08-19; heights vintage 2023) — heights behave like eave/mean height, ~3 m below our LiDAR ridge (MAE 3 m, 9% within 1 m). Fallback only.
- **Google Open Buildings 2.5D Temporal** — no North America coverage. **GlobalBuildingAtlas** (CC BY-NC), **UT-GLOBUS** (9 m RMSE), **3D-GloBFP** (2.4–3.4 m RMSE), **Open City Model 2019** — all far coarser than the scan.

## Dead ends (so nobody re-chases them)

- TNM Access API: only the 16 LPC items already known (2021 GNO ×6, 2002 ×4, 2015/2017 ×6); OPR/DEM product queries return 0 for the bbox.
- 3DEP work-unit index (WESM.gpkg/.csv, `index.nationalmap.gov/.../3DEPElevationIndex`): post-2021 Louisiana units (`LA_CoastalLouisiana_2020_D20`, `LA_CPRA_2019_C20` B1–B5, LWI units) do not reach uptown New Orleans.
- USGS EPT 404s for other guessed names; `usgs.entwine.io/boundaries/resources.geojson` lists only `LA_2021GNO_1_C22`, `LA_UpperDeltaPlain_2017`, `LA_STATEWIDE_2002` here.
- NOAA: 2022 post-Ida topobathy (DAV #10200) and USACE NCMP strips are coastal only; `maps.coast.noaa.gov/.../DAV/ElevationFootprints` is gone (404).
- OpenTopography: catalog API for the bbox returns only global DEMs; the 3DEP subset job needs a .edu login or OT+.
- NCALM (nearest: deltaic wetlands 2023), NASA G-LiHT (no Louisiana flights), NEON (no Louisiana site), NASA CMR: nothing over the campus.
- City: `gis.nola.gov` (30 folders) and `maps.nola.gov` (27 folders) enumerated — footprints, 2017 bare-earth tiles and 2021 Pictometry imagery only; Orleans Parish Assessor is behind a Cloudflare challenge; RPC has only census/transport layers; S&WB requires sign-in.
- NAIPPlus ImageServer: only the May 2023 vintage exists over the campus (no 2021 to match the scan).

## What this means for the pipeline

1. Keep the 2021 QL1 point cloud as the geometry source; spend effort on reconstruction, not acquisition (done: `Docs/accuracy-plan.md`).
2. Use the **2025 LaDOTD 0.15 m RGBI ortho** for colour, NDVI and change detection (`fetch_naip.py --service …`).
3. Merge the **city footprint layer** with OSM (`fetch_footprints.py`, `build_model.py --extra-footprints`), letting the scan decide what is demolished vs built after 2021.
4. Optionally validate the terrain against the LaDOTD 0.5 m bare-earth DEM.
5. If roof detail beyond ±10 cm is ever needed for hero buildings, the honest path is a drone survey (or a Vexcel DSM licence).
