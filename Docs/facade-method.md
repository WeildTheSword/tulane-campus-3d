# Facade method: photo-derived exteriors for the major campus buildings

Status: method spec + Howard-Tilton proof-of-concept. Written 2026-09-07 from four research lanes
(photo-sources, extraction-methods, apply-to-model, poc-howard-tilton) after independent skeptic
verification of every finding. Statements below are marked as follows:

- **verified** - reproduced live by a skeptic against the primary source (API, repo file, photo, licence text) or adjudicated by the PoC judge pass;
- **unverified** - stated by a lane but not reproduced (estimates, untested recipes, secondary numbers);
- **refuted** - the skeptic showed the claim wrong as stated (section 7).

Repo files this document refers to: `build_model.py`, `pack_web.py`, `viewer/scan_template.html`,
`data/osm.geojson`, `out/tulane_enriched.geojson`, `data/facades/howard_tilton.json` (+ `.pass1.json`, `.pass2.json`),
`data/photos/howard_tilton/` (24 open-licence images + `restricted_reference/`), `out/tulane_scan.html`.

Blockers found while researching (all verified):

1. `ANTHROPIC_API_KEY` in this environment is rejected: `GET https://api.anthropic.com/v1/models` returns HTTP 401 `authentication_error: API key is invalid.` No `ant` CLI is installed and no profile exists, so **no Claude vision call has ever completed for this project**. Every VLM stage below is specified from the documentation and the pixel-measurement half was validated by hand-placed boxes.
2. `anthropic` is not installed in `.venv` (a 1.4.0 copy is vendored under the session scratchpad `pylib/`). `pip install anthropic` in `.venv` is required before stage 3.
3. `pack_web.py:92-98` (`decimate`) collapses building walls: the Howard-Tilton mesh in `out/tulane_scan.html` keeps 3 vertical triangles out of 652, and page-wide only 5 % of vertical wall area survives. Nothing in section 4 is visible in the page until this is fixed.
4. Mapillary requires a free registered client token for every request; the project has none (the probe used the OSM iD editor's published token, which must not be shipped).

---

## 1. Recommended method (one paragraph) and licence stance

For each building: **identify** it from its OSM footprint in `data/osm.geojson` (name, `wikidata`, centroid, `building:levels`) plus the LiDAR facts in `out/tulane_enriched.geojson` (height, `height:max`, roof planes, fit rmse); **find photos** by the lookup chain in section 2 (Wikidata P18/P373 -> the Commons category in one API call; else Commons name search / a walk of the 48 campus building subcategories through a hand alias table; Concept3D campus-map images by point-in-polygon for rights-reserved reference; Mapillary 2016 frames for plinth/entrance detail only), download <= 1920 px thumbnails with a sidecar JSON (source URL, author, licence, date, GPS); **triage** the set in one multi-image Claude call that returns, per photo, is-this-the-building / which facade / interior-or-exterior / usable-for-colour / usable-for-grid / does it predate a visible addition relative to the LiDAR date; **extract** semantics with a second Claude call under a JSON schema (material class per element, absolute-pixel box per claim, lit/shadow flag, entrance side, roof-edge type, addition present, explicit `not_visible`); **measure** colour in code from those boxes (sRGB -> CIELAB, sky/vegetation/specular masks, Otsu split to keep the lit mode, chroma shift from a labelled white/neutral element, per-material median across photos with a dE spread) and keep counts, heights and footprints from LiDAR/OSM only; **apply** the resulting facade spec to the meshes (per-building wall/trim/glazing colours and storey/bay parameters via `data/facades/*.json`; the page through `pack_web.py` extras + a procedural shader once walls survive decimation; the engine GLB through `build_model.py` wall colour + private wall vertices; roofs always keep the 2025 orthophoto colour). Licence stance (verified against the CC legal codes, Mapillary ToS, Google ToS/geo-guidelines, Concept3D terms, tulane.edu copyright notice): CC BY 2.0/4.0 pixels may be baked into shipped textures with author + licence + link credit (note the anti-DRM clauses, CC BY 2.0 s.4(a) / 4.0 s.2(a)(5)(C), if the game ships with DRM); CC BY-SA 3.0/4.0 and all Mapillary imagery make any derived texture "Adapted Material" that must itself be CC BY-SA (keep those in a separately licensed atlas or use them for attribute extraction only; Mapillary additionally requires its logo + link when images are served); Tulane/Concept3D rights-reserved images are viewed and measured only, never copied into an asset and never redistributed (kept under `restricted_reference/`); Google Street View / Places Photos are not used at all - Google's terms forbid storing the imagery and its geo-guidelines expressly forbid "using applications to analyze and extract information from the Street View imagery" (the free metadata endpoint may only record where coverage exists). Extracting non-copyrightable facts (paint colour, material, bay count) from any photo is treated as permissible; this is a legal opinion consistent with 17 U.S.C. s.102(b)/Feist, **unverified** against a primary source.

---

## 2. Per-building photo lookup chain

All Wikimedia calls need a descriptive `User-Agent` with real contact info, e.g.
`tulane-campus-3d/1.0 (https://<project-url>; <email>)`. Verified: a generic or missing UA gets HTTP 403
("Please set a user-agent"); the placeholder word "contact" was accepted but is not policy-compliant.
Verified rate limits (Wikimedia_APIs/Rate_limits): User-Agent-only tier = 200 requests/min, <= 3 concurrent,
honour `Retry-After` (observed 33 s; 429s appeared at 12-20 concurrent calls). `titles=` batches cap at 50.
Serialize requests; the lanes hit 429 when several ran at once.

### 2a. Name / Wikidata -> Wikimedia Commons (no key)

| Step | Call | Output | Status |
|---|---|---|---|
| 1. OSM tag | `properties.tags.wikidata` in `data/osm.geojson` | QID for 19 features (12 unique) | verified; only **4 are Tulane campus buildings with a P18 image**: Howard-Tilton Q16466615, Devlin Fieldhouse/Fogelman Arena Q5267618, Yulman Stadium Q8060993, Turchin Stadium Q5605129. Q7851950 (Social Work) is mis-tagged on way 327443290 Mussafer Hall and its P18 is a Gibson Hall datestone; Q18155455 is the streetcar line. |
| 2. Wikidata | `GET https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q16466615&props=claims\|sitelinks\|labels&format=json` -> `claims.P18[].mainsnak.datavalue.value` (image), `claims.P373` (Commons category), `sitelinks.commonswiki` | HT: P18 `Howard Tilton Library NOLA.jpg` (P2096 "Main facade..."), P373 `Howard-Tilton Library`, P625 29.9399/-90.1221, P856 library.tulane.edu | verified |
| 3. Category listing + licence + thumb in one call | `GET https://commons.wikimedia.org/w/api.php?action=query&generator=categorymembers&gcmtitle=Category:Howard-Tilton_Library&gcmtype=file&gcmlimit=100&prop=imageinfo&iiprop=url\|size\|extmetadata\|user&iiurlwidth=1600&iiextmetadatafilter=LicenseShortName\|LicenseUrl\|Artist\|Credit\|ImageDescription\|DateTimeOriginal\|GPSLatitude\|GPSLongitude\|AttributionRequired&format=json` -> `pages[].imageinfo[0].{thumburl,url,width,height,extmetadata.*}` | HT: 33 files in one response (17 CC BY 2.0, 9 CC BY-SA 4.0, 4 CC BY-SA 3.0, 1 CC BY 4.0, 2 PD); 18 exterior / 15 interior-or-other | verified (note: the lane's downloads are 1920 px wide, not 1600) |
| 4. No wikidata: name search | `list=search&srsearch="<building name>" Tulane&srnamespace=6` | HT: 141 hits, recall 33/33 of the category | verified |
| 4b. Name disambiguation | `wbsearchentities?search=<name>&language=en` then require description contains "Tulane" or P625 within ~200 m of the centroid | "Gibson Hall" also returns Q16992820 (London) | verified |
| 5. Campus category walk | `list=categorymembers&cmtitle=Category:Tulane_University_Uptown_Campus_buildings&cmtype=subcat` -> 48 subcats, 642 files; parent holds 65 loose files; `Category:Tulane_University_Uptown_Campus` 390 loose files; `Category:Freret_Street,_Tulane_University` 30 files + 4 subcats (street-level frames 2021-2026, CC BY-SA 4.0) | 4 of the 48 are fields/track/the demolished Tulane Stadium -> ~44 usable | verified |
| 6. Matching OSM names to subcats | difflib on normalised names: cutoff 0.8 -> 25 hits (1 wrong: Cudd->Buddig); cutoff 0.6 -> 43 hits, 14 wrong | **use a hand alias table**, not loose fuzzy matching. Verified aliases: Devlin Fieldhouse = Fogelman Arena; Jones Hall = Joseph Merrick Jones Hall; Cudd Hall = Robert C. Cudd Hall; Tilton Hall = Tilton Memorial Hall; Blessey = Walter E. Blessey Hall; Mayer = Katherine & William Mayer Residences; Greenbaum = Barbara Greenbaum House; Navy Building = Navy R.O.T.C. Building; Newcomb Art Gallery = Woldenberg Art Center; Lindy Boggs = Boggs Center; Warren Hall = Warren House. OSM has 93 named building features (89 unique names). | verified |
| 7. Geosearch (supplementary only) | `list=geosearch&gscoord=<lat>\|<lon>&gsradius=120&gsnamespace=6` | within 100 m of HT: 8 files, 1 of them HT; HT's only geotagged file is 87.5 m out (r=80 misses it); 80-82 files within 600 m of campus centre | verified - thin, use radius >= 120 m |

Per-file EXIF is available via `iiprop=metadata` (verified: the Feb-2026 photo is a Sony ILCE-7RM5, 12 mm, GPS 29.94037/-90.12151, cropped from the native sensor size).

### 2b. Coordinates -> street-level imagery

| Source | Call | Coverage near Howard-Tilton | Key | Status |
|---|---|---|---|---|
| Mapillary v4 | `GET https://graph.mapillary.com/images?access_token=MLY\|...&fields=id,captured_at,compass_angle,computed_compass_angle,computed_geometry,is_pano,sequence,creator,thumb_2048_url&bbox=<lon-0.00115>,<lat-0.001>,<lon+0.00115>,<lat+0.001>&limit=2000`; keep frames with 30 m < distance(camera, centroid) < 110 m and \|bearing(camera->centroid) - computed_compass_angle\| < 30 deg; then `GET https://graph.mapillary.com/<id>?fields=thumb_2048_url` and download at once (fbcdn URLs expire ~30 days) | 150 m box: 632 images / 25 sequences, all March 2016, perspective 1920x1080, 0 panos, 3 uploader accounts (FF_Loc1 215, FF_local 209, Loc_WR 208); whole campus (5x5 grid, a single call fails with "Please reduce the amount of data"): 16,215 images / 234 sequences (2016-02: 483, 2016-03: 13,734, 2016-04: 1,044, 2022-10: 954); nearest 2022 frame 497 m from HT | free client token from https://www.mapillary.com/dashboard/developers (account login). Without a token: error 190; tiles 403 | verified. Value: plinth / ground-floor / entrance materials only (letterboxed dashcam frames, addition under construction in 2016). The lane's smaller bbox (+-0.0006/+-0.0005) excludes all three frames it downloaded - use the widened box above. Even with `computed_compass_angle` one of three frames was mis-aimed: **visually verify every frame**. Licence CC BY-SA 4.0 + Mapillary logo/link; ToS s.12 adds obligations for commercial use. |
| Google Street View Static / Places Photos | metadata only: `GET https://maps.googleapis.com/maps/api/streetview/metadata?location=<lat>,<lng>&source=outdoor&radius=60&key=KEY` -> `pano_id,date,status` (no charge, no quota) | not tested (no key) | Google Cloud project + billing + API key | verified ToS: **do not use images** (Terms 3.2.3(a)(i) storing, (b) caching, (c) creating content; geo-guidelines: no screenshots "for any purpose", no "analyze and extract information from the Street View imagery"). Store lat/lng + date, not `pano_id` (docs say IDs change). A human eyeballing Street View and writing colours into the model is a grey area, not cleared. |
| Panoramax | `https://api.panoramax.xyz/api/search?bbox=-90.135,29.930,-90.110,29.950` | 0 features (wider NOLA bbox returns hits, so the zero is real) | none | verified |
| KartaView | `https://api.openstreetcam.org/2.0/photo/?lat=29.9399&lng=-90.12224&radius=300` | empty | none | verified |
| Flickr | `flickr.photos.search&lat=&lon=&radius=0.1&radius_units=km&license=4,5,7,9,10,11,12&has_geo=1&extras=url_o,url_l,license,owner_name,geo,date_taken` **plus a limiting agent** (`text=<building name>` or `min_taken_date=1990-01-01`; without one only the last 12 hours are returned) | not tested | free API key | recipe verified against docs; results unverified. Licence ids: 4=BY 2.0, 5=BY-SA 2.0, 7=no known restrictions, 9=CC0, 10=PDM, 11=BY 4.0, 12=BY-SA 4.0 |
| Bing Streetside / Apple Look Around / DPLA / Louisiana Digital Library | - | retired Oct 2025 / display-only / needs key / WAF-blocked | - | unverified (lane report only) |

### 2c. Tulane's own campus map (Concept3D) - rights-reserved reference images

`campusmap.tulane.edu` does not resolve; `https://map.tulane.edu/` 301-redirects to `https://map.concept3d.com/?id=1015`.
The map's public client key is embedded in its JS bundle (`https://map.concept3d.com/js/index.js`). All verified:

- `GET https://api.concept3d.com/locations?map=1015&key=0001085cc708b9cef47080f064612ca5` -> 1,267 locations (`id,name,catId,lat,lng,...`; no address field). `catId 18314` = "Campus Buildings" (48 locations, 48/48 with media: 284 images + 5 YouTube links; use `mediaUrlTypes == 'image'`), `catId 18317` = "Residence Halls" (15, not fetched).
- `GET https://api.concept3d.com/locations/<id>?map=1015&key=...` -> `mediaUrls[]`, `description` (HTML; carries architect/year/style, e.g. Tilton Memorial Hall "Constructed in 1902 ... Andry and Bendernagel in the neo-Romanesque style"). Assets at `https://assets.concept3d.com/assets/<mediaUrl>`. Howard-Tilton = location 188134, 4 images (2 professional exteriors, 1 photographed 1960s elevation drawing, 1 interior).
- Matching: point-in-polygon of the 1,267 points against OSM footprints hits 62 named + 40 unnamed footprints; 40 named footprints carry at least one Concept3D exterior image. Prefer this spatial match over name matching ("Tilton Memorial Hall" and "Howard-Tilton Memorial Library" are both in 18314, 481 m apart). Per-building image counts: Richardson Memorial 13, Gibson/Hebert/Blessey/Boggs/Paul Hall 12, Dinwiddie/Stern 11, Tilton/Stanley Thomas/Turchin 10, Yulman 8, Howard-Tilton 4, Wilson Center 1.
- Terms: Concept3D end-user terms forbid copying/mirroring except "for Your own internal business purposes" and forbid derivative works; tulane.edu/copyright-notice allows download only for personal non-commercial use. Use of the API key is an undocumented, ToS-grey use. Treatment: analysis-only, files under `restricted_reference/`, never in a shipped asset. Two more Tulane-copyright photos exist at `https://library.tulane.edu/sites/default/files/2025-04/howard-tilton-memorial-library-5.jpg` and `-6.jpg` (HTTP 200, 368x544; the lane's "404" claim was wrong).

### 2d. Address-only features

Addresses are not needed for named buildings (the footprint centroid is always available). For the 1,903 addressed, unnamed features (private houses): Nominatim on "7001 Freret St" returns street-segment interpolations 100 m and 332 m from the library (verified) and its policy discourages bulk use; the US Census batch geocoder (`geocoding.geo.census.gov/.../onelineaddress?...&benchmark=Public_AR_Current`) landed 60 m off (verified). The only imagery for houses is Mapillary 2016 ground level; the typology fallback in section 4 covers them.

---

## 3. Extraction pipeline

### 3a. Stage list (per building)

| # | Stage | Tool | Status |
|---|---|---|---|
| 0 | Fetch photos + sidecars (section 2), <= 10 files, <= 1920 px, < 5 MB each | requests | verified for HT (18 Commons + 3 Mapillary + 4 Concept3D) |
| 1 | Triage: one multi-image Claude call (photos resized to 800 px, ~580 visual tokens each; 4:3 photos cost 638, budget 640) returning per photo `{is_target, facade_side, interior, usable_for_colour, usable_for_grid, issues[], predates_visible_addition}`; the prompt carries LiDAR facts (height, levels, roof shape, scan year 2021) and the sidecar date | claude-opus-5, `output_config.format = json_schema`, `output_config.effort = low` | design verified against docs; **never executed** (401). Need is verified: of the 6 first Commons hits for HT, 2 were interior, 2 pre-addition (2001/2002), 1 scaffolded/blown-out, 1 clean. Any HT photo before 2016 is stale for storeys/roof edge (addition announced Aug 2013, under construction Dec 2014, contractor completion 2015, opened Jan 2016; library.tulane.edu calls it "the 2016 expansion"). |
| 2 | Semantic extraction: best 2-3 photos, pre-resized with the documented `resized_size(w, h, max_edge=2576, max_tokens=4784)` (Claude 4.7+/Opus 5 high-res tier; 28x28-px patches; tokens = ceil(w/28)*ceil(h/28)), sent with `transformations: {oversized_image: "error"}` so returned pixel coordinates map 1:1; schema demands 6-12 single-material regions as absolute-pixel boxes (min 30x30 px, avoid members < 20 px or crop-and-zoom), material class, finish, lit/shadow flag, occluded fraction, hex guess, and `not_visible` enums; prompt asks the model to report contradictions with the LiDAR facts rather than reconcile them | claude-opus-5 structured outputs | design verified against docs; **never executed**. Schema caveat (verified): structured outputs do not support `minItems`/`maxItems` beyond 0/1 or numeric bounds - encode a box as `{x1,y1,x2,y2}` integers and clamp fractions in code. |
| 3 | Colour measurement in code (section 3b) | numpy/scikit-image | **verified on two HT photos** |
| 4 | Window lattice from rectified photos | OpenCV LSD + vanishing points | **refuted as specified** (section 7); replacement rule in 3d |
| 5 | Judge: text-only comparison of two extraction passes + measured colours -> conflicts, human queue | claude-opus-5 | design only; the HT PoC did this by hand (section 6) |
| 6 | Human QA on a contact sheet (photo + boxes + swatches + spec) | - | 3-5 min/building (estimate) |

### 3b. Colour measurement procedure (verified on `Howard-Tilton ... February 2026.jpg` CC BY 4.0 and `Howard Tilton Library NOLA.jpg` CC BY 2.0)

1. Crop each VLM box; convert sRGB -> linear -> CIELAB (`skimage.color.rgb2lab`).
2. Masks: sky `b* < -12 & L* > 55`; vegetation `2G-R-B > 0.08 & a* < -8`; specular any channel > 0.985; black `L* < 6`.
3. If the L* range > 25, Otsu-split L* and keep the upper (lit) mode when both modes hold > 15 % of pixels and are > 18 L* apart.
4. Report median Lab, MAD, pixel count, rejection fractions; reject a region if < 50 pixels remain, any rejection fraction > 0.5, or MAD(L*) > 12.
5. White balance: subtract the (a*, b*) of a labelled matte painted-white or neutral element in the same photo; else grey-world over the building regions only. (The HT white reference was a glossy white metal frame; its b* = -8.7 is partly sky reflection - prefer matte references.)
6. Albedo: scale luminance so the white reference reads L* 93; shadowed patches must agree in chroma within dE 5, else flag.
7. Merge photos per material: median albedo Lab, sigma = dE spread; accept when n_photos >= 2 and sigma < 6, else `needs_more_photos`.
8. Store the VLM hex guess and its dE to the measurement; dE > 15 -> second look / human queue.

Why (verified numbers): the five sunlit precast boxes on the 2026 photo give mean-of-medians Lab 77.5/2.1/0.5 (#c4bebf), whereas the naive RGB mean of the same boxes is #8e8a85..#9f9fa7 (dE 12.7-20.1, shadow + sky contamination). The 2001 photo gives 85.8/-4.0/7.7; the white-reference chroma shift cuts the cross-photo chroma disagreement from dE 9.4 to 5.3 (full dE 9.9, mostly exposure). `build_model.py:369 WALL = [214,206,194]` is Lab 83.1/0.7/7.0 - dE 6.0 from the shifted HT precast, so beige is roughly right for this one building and will be far off for brick.

VLM colour guesses are hints only: ColorBench (arXiv 2504.10514) colour-extraction multiple choice GPT-4o 40.6 %, Gemini-2-Flash 52.1 %, best open model 57.3 %; "Color Names in VLMs" (arXiv 2509.22524) reports performance dropping on non-prototypical colours. Neither benchmark evaluates a Claude model (verified).

### 3c. Attribute trust map (verified; storey rule corrected)

| Source of truth | Attributes |
|---|---|
| Photos, after measurement | material class per element; albedo colour; finish/texture class; glazing tint and frame colour; window shape and w/h ratio; bay pitch as a ratio of storey height; ground-floor vs upper storey height ratio; entrance facade + relative position + type; roof-edge type (overhang/parapet/cornice); recessed ground floor / colonnade presence; ornament list; plinth material |
| LiDAR / OSM only | footprint; absolute height, eave/ridge; roof shape, pitch, planes; roof-level overhang outline; rooftop units (`height:max` = highest LiDAR cell minus base, `build_model.py:457`; "rooftop unit" is an inference); facade lengths for count extrapolation; orientation |
| Storey count | `building:levels` when present (`source = osm`); otherwise LiDAR height / a typology storey height (campus median 4.87 m for the 33 buildings with both height and levels; p10 3.69, p90 6.38; dormitories/houses ~3.0-3.6 m; repo fallback `levels*3.5+1.0` at `build_model.py:504`). **Never a fixed 3.3-4.2 m band** - it gives 6.8-8.6 storeys for Howard-Tilton (28.4 m / 6 levels = 4.73 m) and misses 82 % of campus buildings. A photo may only confirm within +-1. |
| Never from one photo | metric setback depth; absolute window sizes; counts on occluded/oblique facades; storey count |

Anthropic's vision docs state that coordinate/localization outputs are approximate and counts may be inexact (verified quotes); GATA2Floor (arXiv 2605.11863) shows facade-element detection, not floor counting, is the fragile step (0.26 floors MAE with annotated detections vs 3.04 with label-free proposals that GPT-4o merely verified). Every spec field carries a `source` so the packer knows what it may override.

### 3d. Window grid rule (replacement for the refuted lattice recipe)

Rectify with the focal-free path only (LSD -> RANSAC vertical + facade-horizontal vanishing points on the building band -> send the vanishing line to infinity -> affine shear; residuals < 0.25 deg in 0.6 s on the M1, verified) and then fix scale **per axis** from two metric constraints already known: vertical = LiDAR eave height between detected ground line and roofline; horizontal = the OSM footprint edge length between two visible corners (HT: 87.0 / 46.0 m). For fin/brise-soleil facades take the pitch from the autocorrelation of rectified vertical-segment x-positions; use box detection only for discrete openings. Store per-zone rows (HT has four: ground storefront, fin floors 2-3, balcony band 4, two-storey hood 5-6). Report `visible_count` and `extrapolated_count = round(facade length / pitch)`; accuracy is unmeasured until validated against a manual count. `opencv-python-headless 5.0.0.93` installs on arm64/py3.13 but is not in `.venv`.

### 3e. Facade-spec JSON schema (FacadeSpec v1, proposed)

Three shapes currently coexist and must be reconciled before scaling: (i) this proposed schema (extraction lane), (ii) the judge's richer ad-hoc structure actually written to `data/facades/howard_tilton.json` (`building / storeys / facade.{wall,structural_bays,trim,glazing,base,roof_edge,upper_addition} / per_attribute_confidence / cross_checks_lidar / render_recommendations`), and (iii) the apply lane's flat render parameters (`wall, trim, glass, frame, storey_h, storeys, bay, win_w, win_h, sill, ground{}, crown{}`) in its scratch `facades.json`. Recommendation: keep (ii) as the human-readable evidence record and generate (iii) from it as the packer input; fold `source` and `bbox` fields from (i) into (ii).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "FacadeSpec v1",
  "type": "object",
  "required": ["building", "lidar", "provenance", "storeys", "materials", "facades", "roof_edge", "confidence"],
  "properties": {
    "building": {"type": "object", "properties": {"slug": {"type": "string"}, "name": {"type": "string"}, "osm_id": {"type": "integer"}, "wikidata": {"type": "string"}, "address": {"type": "string"}, "centroid_lonlat": {"type": "array", "items": {"type": "number"}}}},
    "lidar": {"description": "copied from tulane_enriched.geojson; read-only for the facade pipeline", "type": "object", "properties": {"height_m": {"type": "number"}, "height_max_m": {"type": "number"}, "roof_shape": {"type": "string"}, "roof_planes": {"type": "integer"}, "fit_rmse": {"type": "number"}, "levels_osm": {"type": "integer"}, "scan_date": {"type": "string"}}},
    "provenance": {"type": "object", "properties": {
      "photos": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "file": {"type": "string"}, "source_url": {"type": "string"}, "author": {"type": "string"}, "license": {"type": "string"}, "date_taken": {"type": "string"}, "view": {"type": "string"}, "usable_for": {"type": "array", "items": {"type": "string", "enum": ["colour", "grid", "entrance", "roof_edge", "none"]}}, "stale": {"type": "boolean"}, "issues": {"type": "array", "items": {"type": "string"}}}}},
      "extractor": {"type": "object", "properties": {"model": {"type": "string"}, "prompt_version": {"type": "string"}, "run_date": {"type": "string"}, "passes": {"type": "integer"}}},
      "qa": {"type": "object", "properties": {"human_checked": {"type": "boolean"}, "checker": {"type": "string"}, "notes": {"type": "string"}}}}},
    "style": {"type": "object", "properties": {"period": {"type": "string"}, "style": {"type": "string"}, "massing_notes": {"type": "string"}}},
    "storeys": {"type": "object", "properties": {"count": {"type": "integer"}, "source": {"type": "string", "enum": ["lidar_osm", "lidar_only", "osm_only"]}, "ground_floor_height_ratio": {"type": "number"}, "top_floor_height_ratio": {"type": "number"}, "photo_agrees": {"type": "boolean"}}},
    "materials": {"type": "array", "items": {"type": "object", "required": ["id", "class", "colour"], "properties": {
      "id": {"type": "string"},
      "class": {"type": "string", "enum": ["precast_concrete", "cast_in_place_concrete", "exposed_aggregate_concrete", "brick", "stone", "stucco_or_plaster", "painted_metal", "anodized_metal", "glass", "wood", "terracotta", "tile", "unknown"]},
      "finish": {"type": "string"}, "pattern": {"type": "string"},
      "colour": {"type": "object", "properties": {"appearance_lab": {"type": "array", "items": {"type": "number"}}, "albedo_lab": {"type": "array", "items": {"type": "number"}}, "albedo_hex": {"type": "string"}, "sigma_dE": {"type": "number"}, "n_photos": {"type": "integer"}, "n_regions": {"type": "integer"}, "method": {"type": "string", "enum": ["median_lit_whiteref", "median_lit_greyworld", "median_all", "vlm_guess_only"]}, "vlm_hex_guess": {"type": "string"}, "dE_vlm_vs_measured": {"type": "number"}}},
      "regions": {"type": "array", "items": {"type": "object", "properties": {"photo_id": {"type": "string"}, "bbox": {"type": "object", "additionalProperties": false, "required": ["x1", "y1", "x2", "y2"], "properties": {"x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}}}, "lit": {"type": "boolean"}, "occluded_fraction": {"type": "number"}}}},
      "pbr": {"type": "object", "properties": {"library_match": {"type": "string"}, "roughness": {"type": "number"}, "tint_multiplier_linear_rgb": {"type": "array", "items": {"type": "number"}}}},
      "confidence": {"type": "number"}}}},
    "facades": {"type": "array", "items": {"type": "object", "required": ["side", "wall_material"], "properties": {
      "side": {"type": "string"}, "visible_in": {"type": "array", "items": {"type": "string"}}, "wall_material": {"type": "string"},
      "secondary_materials": {"type": "array", "items": {"type": "object", "properties": {"material": {"type": "string"}, "where": {"type": "string"}, "area_fraction": {"type": "number"}}}},
      "base": {"type": "object", "properties": {"material": {"type": "string"}, "height_ratio_of_storey": {"type": "number"}}},
      "bays": {"type": "object", "properties": {"pitch_over_storey_height": {"type": "number"}, "pitch_m": {"type": "number"}, "visible_count": {"type": "integer"}, "extrapolated_count": {"type": "integer"}, "regularity": {"type": "number"}, "source": {"type": "string"}}},
      "window_grid": {"type": "array", "items": {"type": "object", "properties": {"storey_from": {"type": "integer"}, "storey_to": {"type": "integer"}, "rows_per_storey": {"type": "integer"}, "y_frac_in_storey": {"type": "number"}, "shape": {"type": "string"}, "w_over_h": {"type": "number"}, "width_over_bay": {"type": "number"}, "frame_material": {"type": "string"}, "glass_material": {"type": "string"}, "recess_ratio": {"type": "number"}, "spandrel_material": {"type": "string"}}}},
      "setback": {"type": "object", "properties": {"recessed_ground_floor": {"type": "boolean"}, "colonnade": {"type": "boolean"}, "recess_m": {"type": "number"}, "source": {"type": "string", "enum": ["mono_depth", "vlm", "none"]}, "confidence": {"type": "string"}}},
      "entrance": {"type": "object", "properties": {"present": {"type": "boolean"}, "x_frac": {"type": "number"}, "type": {"type": "string"}, "width_over_bay": {"type": "number"}, "canopy": {"type": "boolean"}}},
      "ornament": {"type": "array", "items": {"type": "string"}}}}},
    "roof_edge": {"type": "object", "properties": {"type": {"type": "string", "enum": ["overhang", "parapet", "cornice", "eave", "not_visible"]}, "fascia_material": {"type": "string"}, "overhang_source": {"type": "string", "enum": ["lidar", "photo", "none"]}, "overhang_m": {"type": "number"}}},
    "trim": {"type": "array", "items": {"type": "object", "properties": {"where": {"type": "string"}, "material": {"type": "string"}}}},
    "render_hints": {"type": "object", "properties": {"lod1_wall_rgb": {"type": "array", "items": {"type": "integer"}}, "lod1_trim_rgb": {"type": "array", "items": {"type": "integer"}}, "lod1_glass_rgb": {"type": "array", "items": {"type": "integer"}}, "atlas": {"type": "string"}}},
    "confidence": {"type": "object", "properties": {"materials": {"type": "number"}, "colour": {"type": "number"}, "grid": {"type": "number"}, "entrance": {"type": "number"}, "needs_more_photos": {"type": "boolean"}, "conflicts": {"type": "array", "items": {"type": "string"}}}}
  }
}
```

The `regions[].bbox` object form replaces the lane's `minItems: 4 / maxItems: 4` array, which Claude structured outputs reject (verified). Roof colour is deliberately absent: roofs keep the orthophoto.

---

## 4. Applying a spec to our meshes

### 4a. Ground truth about the meshes (all verified)

- `build_model.py:353` `At = vid[...]; Bt = vid[...]` reuses roof-grid vertices as wall tops; `:354-356` create only the bottom vertices; `:369` `WALL = [214,206,194,255]`; `:371-377` `color_vertices` tiles WALL and overwrites `is_top` vertices (which include every wall top) with the orthophoto. Consequence in the engine GLB: every wall quad shades from roof colour at the top to beige at the bottom. Call sites: `:512` (OSM buildings), `:520` (tiny-footprint `extrude_polygon` path, `:513-519`), `:573` (scan-only structures). Building props: `:65-75`; typology height dict `:504`.
- Walls are 1 m grid staircases. Howard-Tilton (out/core, mesh `Howard Tilton Memorial Library#2711`): 4,804 verts, 8,628 faces, 652 vertical faces = 326 quads each exactly 1.0 m wide on 121 distinct axis-aligned planes (median 3 quads/plane) because the footprint is 16.2 deg off the St. Charles-aligned frame (bearing 104.0 deg, `out/core/build.log`). Normal-only facade classification mislabels 148/652 = 22.7 % of wall faces (the step faces); a world projection onto the MABR tangent (phi = 106.3 deg in glTF xz) gives a continuous `u` along the true facade (class spans 88.2 / 47.1 m).
- `pack_web.py:92-98` `decimate()` runs `fast_simplification.simplify(agg=6)` on the raw mesh whose wall bottoms are an open boundary, so QEM collapses wall bottoms into the roof edge at zero error: HT at `--decimate-named 0.4` -> 14 vertical + 348 tilted faces; at 0.7 -> 0 vertical. The published `out/tulane_scan.html` (12,646,952 bytes = 12.06 MiB) was packed from **out/core_v2** (83 named + 2,486 unnamed = 2,569 buildings; HT node 2717 verts / 5176 tris, 3 vertical faces), not from `out/core + out/core3` as README:37 / HANDOFF:78 say. Page-wide retention of vertical wall area: 5 % (named median 0.09, unnamed median 0.00).
- `viewer/scan_template.html:136` `MeshStandardMaterial({vertexColors, flatShading:true})`; `:153-156` `addFitColors` builds a per-vertex attribute at load from `userData.ranges` (`[offset, count, fit]` - no phi/base shipped); `:158` `setFitMode`; `:205` dock-button pattern. three.js r128 include order verified: `color_fragment` (30) < `normal_fragment_begin` (35, FLAT_SHADED normal from `dFdx/dFdy`) < `normal_fragment_maps` (36) < `lights_physical_fragment` (41), so a `diffuseColor` override injected after `#include <normal_fragment_maps>` is consumed by the BRDF; `COLOR_0` is VEC4 (`pack_web.py:63`) so `USE_COLOR_ALPHA` is defined; `customProgramCacheKey` lets all buildings share one program.

### 4b. Work order

| # | Change | Where | Verified effect | Page size |
|---|---|---|---|---|
| 1 | **Cap-then-strip decimation** (required): merge the duplicated bottom vertices, fan-cap the open bottom to its centroid, `simplify`, drop faces with all three vertices at `y_min`, re-attach colours by nearest original vertex | replace `pack_web.py:92-98` `decimate()` (prototype `decimate_keep_walls` in the session scratchpad `facade_walls.py`) | HT keeps 652/652 vertical faces at 0.4 and at 0.7; roof 7,976 -> 4,394 faces; in a full core_v2 repack all 83 named buildings keep >= 90 % of vertical wall area | **12.06 -> 11.47 MiB** (smaller, because the duplicated bottoms merge). Alternative `--decimate-named 0`: 14.37 MiB. Unnamed houses at `--decimate 0.7` keep only median 54 % of wall area even with the cap (1,163 of 2,486 lose more than half) - lower the fraction for unnamed or accept it |
| 2 | Ship `phi`, `base`, `h` per named mesh (from the MABR of the wall-bottom vertices, computed **before** decimation) and `[off, len, fit, phi, base, typ]` per unnamed range; add `--facades data/facades.json` and a `__FACADES_JSON__` template slot | `pack_web.py:122` (named extras), `:133` (ranges), `:161-163` (template fill), `:20-30` (args); template slot after `viewer/scan_template.html:97` | mechanism verified (GLB writer already emits `extras`); numbers unverified | ~36 KB extras + 12-20 KB JSON (lane estimate) |
| 3 | Procedural facade shader: `onBeforeCompile` on the named-mesh material, world position varying from `modelMatrix * transformed` (node scale is inside `modelMatrix`, so units are metres), per-face flat normal -> `wallness = 1 - |n_world.y| > 0.9`, `u = dot(p.xz, facade tangent from phi)`, `v = y - base`; storeys, slab bands, window cells, ground-floor glazing, crown storeys from the spec; roofs untouched (vertex colour path) | `viewer/scan_template.html:136` (material), `:158` (uFacade = 0 in fit mode), `:205` (dock button) | compiles under SwiftShader headless with glErr 0 (verified) **only on a cap-decimated mesh**; on the shipped mesh it paints ~10 % of HT wall area and 18 % campus-wide (section 7). Depends on step 1. | ~3 KB |
| 4 | Engine GLB: per-building wall colour + private wall-top vertices | `build_model.py:369` (`FACADES` load + `wall_rgb(p)` from `p['name']` / `p['building']`), `:371-377` (`color_vertices(..., wall=)`), `:512`, `:520`; wall split at `:353-356` (duplicate `At/Bt` into new non-top vertices; HT +470 verts = 1.44 per wall quad) | change sites verified; not implemented | engine GLB only (38-40 MB; negligible) |
| 5 | Exact-polygon walls (durable fix): keep the heightfield roof, emit one quad per densified OSM ring edge with the top sampled from the fitted `top` field, clip boundary roof cells to the polygon | `build_model.py:511` (`walls=False` + skirt), extend the existing `extrude_polygon` path at `:513-519`; tracked in `Docs/accuracy-plan.md` §4 item 2 | named buildings: 22,628 staircase quads -> 1,941 polygon-edge quads (p50 15 edges) = about -91 %; true facade normals make `phi` unnecessary | roughly -0.3 MB (unverified) |
| 6 | Typology fallback when no photos: `facades.json.typology_defaults` keyed by `building=*` with a height rule for `building=yes` (<= 9 m house, 9-16 m apartments, > 16 m university); `storey_h = height / building:levels` when levels exist | pack-time | unverified (lane proposal) | - |
| 7 | Hero photogrammetry swap (Polycam/Luma capture registered to the OSM outline by MABR angle + 2-D Umeyama + ICP, then replacing the named node) | new `register_hero.py`; `pack_web.py:119-122` `--hero`; template `:136` texture material | unverified (no capture exists); Umeyama recovered a synthetic transform on HT | ~0.8 MB per hero (estimate); page cap 16 MB allows ~3 |

Roof rule (verified): roofs keep the 2025-orthophoto vertex colour; `facades.json` never overrides roofs; the wall-top leak is fixed by the vertex split, not by recolouring roofs. Do **not** flatten single-plane roofs to a median - on Howard-Tilton the dark 27.5 % of roof vertices are PV arrays (blue-shifted, median [100,101,112]), and the current builds (`out/core_v2`, `out/`) give a neutral membrane median [183,186,180] and pale rooftop units [173,185,183]; the lane's grey-penthouse numbers came from the superseded NAIP-coloured `out/core*` builds.

Photo directory hygiene (verified): two directories exist for one building (`data/photos/howard_tilton/` with `<file>.jpg.json` sidecars and `data/photos/howard_tilton_memorial_library/` with `<stem>.json`); consolidate to one slug and one sidecar convention before scaling.

---

## 5. Cost and time

Token counts use the documented formula (ceil(w/28)*ceil(h/28); high-res tier 2576 px / 4784 tokens) and the pricing table (claude-opus-5 $5 in / $25 out per MTok, batch half; claude-sonnet-5 $2 / $10; claude-haiku-4-5 $1 / $5). **No call has run, so every dollar figure is an estimate**; the skeptics independently recomputed the triage (~$0.07) and extraction (~$0.18-0.20) stages and found them consistent. Opus 5 thinks by default and thinking bills as output: set `output_config.effort` low on triage and judge.

| Stage | LLM calls | In / out tokens | Opus 5 | Sonnet 5 | Machine | Human |
|---|---|---|---|---|---|---|
| 0 fetch (<= 10 thumbs + sidecars, serialized) | 0 | - | $0 | $0 | 1-2 min | 0 |
| 1 triage (10 photos @ 800 px = ~5,800 + 500 prompt) | 1 | 6,300 / 1,600 | $0.07 | $0.03 | 20-60 s | 0 |
| 2 extraction (3 photos @ 1600 px = 6,786 + 1,500 schema/prompt; ~3k JSON + ~2k thinking out) | 1 | 8,300 / 5,000 | $0.17 | $0.07 | 40-120 s | 0 |
| 3 colour measurement + merge (numpy) | 0 | - | $0 | $0 | < 1 s | 0 |
| 4 rectification / pitch (OpenCV) | 0 | - | $0 | $0 | 5-20 s | 0 |
| 5 judge (text-only) | 1 | 4,000 / 2,000 | $0.07 | $0.03 | 20-60 s | 0 |
| 6 human QA contact sheet | 0 | - | $0 | $0 | 0 | 3-5 min |
| **Per building** | 3 | 18,600 / 8,600 | **$0.31** ($0.16 batch) | $0.12 ($0.06 batch) | 3-5 min | 3-5 min |
| **83 named buildings** (the page's named meshes) | 249 | | **~$26** (~$13 batch) | ~$10 (~$5 batch) | 4-7 h serial, ~1 h at 8-way or one Batch job | 4-7 h |
| optional second extraction pass | +1 | | +$0.17 | +$0.07 | | |

"~80 buildings" = the 83 named meshes `pack_web.is_named` selects (89 unique named buildings in OSM); the engine-side selection rule (e.g. named or height > N m) is still to be written. The Howard-Tilton PoC, done by hand with three passes over 28 images, took far longer than the per-building budget; the budget assumes the automated path.

---

## 6. Howard-Tilton Memorial Library proof-of-concept

Building: OSM way 327443277, Wikidata Q16466615, 7001 Freret St. LiDAR (`out/tulane_enriched.geojson`, verified): height 28.4 m, `height:max` 32.6 m (the prompt's 32.3 is from out/core_v2), 1 roof plane, `fit:rmse` 0.04 (0.06 is `fit:p90`), `building:levels` 6. Footprint 87.0 x 46.0 m (MABR; long axis 31.6 deg), corners in the spec. Faces: SSW 46 m = Freret St; ESE 87 m = campus / Newcomb Place (entrance, loggia); NNE 46 m = rear toward Dixon Hall; WNW 87 m = Audubon St side.

### 6a. Photo inventory (from the judge's provenance list; licences verified live against Commons `extmetadata`)

| File (`data/photos/howard_tilton/`) | Source / licence | Author | Date | Judge viewpoint | Weight |
|---|---|---|---|---|---|
| Howard-Tilton_Memorial_Library_-_Tulane_University_February_2026.jpg | Commons, CC BY 4.0 | ajay_suresh | 2026-02-05 | ESE face from the E/NE, NNE grazing; 8172 px original; best single reference | high |
| FreretTulane27Dec07HTLibraryA.jpg | Commons, CC BY-SA 3.0 | Infrogmation of New Orleans | 2007-12-27 | SSW (Freret) W half + ground floor, pre-addition, low sun; slit rhythm + sill panels | high |
| FreretTulane27Dec07HTLibraryB.jpg | Commons, CC BY-SA 3.0 | Infrogmation | 2007-12-27 | SSW through oaks | low |
| Freret_Street_..._22_November_2021_-_03.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2021-11-22 | SSW, scaffold canopy (transient), backlit | low |
| Freret_Street_..._22_November_2021_-_04.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2021-11-22 | SSW oblique; red-brown sill panels still present; backlit | medium |
| Freret_Street_14th_Ward_New_Orleans_April_2019_05.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2019-04-11 | S corner from across Freret: SSW addition slots + recessed bays, ESE loggia | high |
| Freret_Street_14th_Ward_New_Orleans_April_2019_06.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2019-04-11 | same, shifted | medium |
| Freret_Street_at_Newcomb_Place_Tulane_University_May_2026.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2026-05-05 | library at far left edge only | none |
| Howard-Tilton_windows_at_night.jpg | Commons, CC BY 2.0 | Tulane Public Relations | 2011-01-13 | interior through ground-floor glass | none |
| Howard_Tilton_8575330378_.jpg | Commons, CC BY 2.0 | Tulane Public Relations | 2013-03-19 | SSW/ESE behind azaleas, pre-addition, soft | low |
| Howard_Tilton_Library_3641474690_.jpg | Commons, CC BY 2.0 | Tulane Public Relations | 2002-07-23 | behind live oak | low |
| Howard_Tilton_Library_NOLA.jpg (Wikidata P18; "(c) TULANE UNIVERSITY" watermark) | Commons, CC BY 2.0 | Tulane Public Relations | 2001-08-20 | ground-floor close-up, sunlit; exposed-aggregate texture, bronze glass, planters | high |
| Howard_Tilton_Library_..._Huey_P._Long_Bridge_..._2002.jpg | Commons, CC BY 2.0 | Tulane Public Relations | 2002-12-02 | storey-4 terrace from a rooftop to the S; original slab, balustrade | medium |
| Newcomb_Blvd_New_Orleans_1st_Nov_2019_18.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2019-11-01 | from Freret near Newcomb Blvd: SSW face + ESE loggia; settled the W-end recessed bays | high |
| Newcomb_Blvd_New_Orleans_1st_Nov_2019_19.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2019-11-01 | same as 18 | medium |
| Tulane80sNewcombTennis.jpg | Commons, CC BY-SA 3.0 | Infrogmation | c. 1980-82 | ESE from the tennis courts, B&W, pre-addition massing | low |
| Tulane_U_Mch2013_HT_Library_Back.JPG | Commons, CC BY-SA 3.0 | Infrogmation | 2013-03-20 | WNW face from the NW corner, NNE grazing; renovation ducts (transient) | medium |
| Tulane_University_Uptown_Campus_23_March_2023_-_01.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2023-03-23 | WNW addition distant; chapel at right fixes the NW neighbours | low |
| Tulane_University_Uptown_New_Orleans_29th_March_2019_04.jpg | Commons, CC BY-SA 4.0 | Infrogmation | 2019-03-29 | **judge relabel: NNE face from its E end**, even light; key precast colour reference | high |
| Zimple_Audubon_Tulane_Library_Construction_Dec14.jpg | Commons, CC BY 2.0 | Infrogmation | 2014-12-22 | WNW, addition frame under red weather barrier; confirms exactly 2 added storeys | medium |
| Zimple_Street_New_Orleans.jpg | Commons, CC BY 2.0 | Infrogmation | 2018-05-01 | **judge relabel: WNW face from the NW**, overcast; addition slots + 3 recessed bays at the S end | high |
| mapillary_1472902660755340.jpg | Mapillary, CC BY-SA 4.0 (+logo/link) | Loc_WR | 2016-03-31 | ESE ground floor / plinth from the campus drive, letterboxed 1080p | low |
| mapillary_29707564172191524.jpg | Mapillary, CC BY-SA 4.0 | Loc_WR | 2016-03-20 | ground/1st floor behind construction fence | low |
| mapillary_1230697741787771.jpg | Mapillary, CC BY-SA 4.0 | Loc_WR | 2016-03-20 | mis-aimed (houses across the street) | none |
| restricted_reference/c3d_HTML_Elevation.jpeg | Concept3D loc 188134, **all rights reserved (Tulane)** | Tulane (unattributed) | - | photographed "Newcomb Place Elevation" drawing, Nolan Norman & Nolan: 11 bays, 6 windows per bay | high (reference only) |
| restricted_reference/c3d_HTML.png | Concept3D, all rights reserved | Tulane | - | ESE face at twilight from the drop-off loop | high (reference only) |
| restricted_reference/c3d_HTML_pic_3.jpg | Concept3D, all rights reserved | Tulane | - | from Freret at Newcomb Place: SSW face left, ESE loggia right | high (reference only) |
| restricted_reference/c3d_HTML_pic_2.jpg | Concept3D, all rights reserved | Tulane | - | interior stacks | none |

Not downloaded (verified interior/painting/other): 2012/2013 studying/reading/shelves photos, Girl in the Library, Howard Tilton Library (5492834898), Computers 2010, Ground floor lobby April 2013, Library Window (3639472120), Reading ... July 2003, Student in Library July 2007, Studying with a view, the two 1899 Dodge paintings. Nine "Freret Street" frames at McAlister that show Percival Stern Hall (pilotis + slit windows, a look-alike) were excluded after inspection (PoC lane, unverified by skeptic).

### 6b. Final spec (judge pass, `data/facades/howard_tilton.json`; pass 1 and pass 2 preserved as `.pass1.json` / `.pass2.json`)

Massing: 6 storeys = 4 original (1968, Nolan Norman & Nolan) + 2-storey addition (2014-2016, Eskew+Dumez+Ripple; Tulane's page calls it "the 2016 expansion", EDR lists completion 2015). Storey heights (confidence 0.55): ground on plinth 4.8, fin floors 4.0 + 4.0, terrace floor 4.2 + 0.7 m slab = 17.7 m original cornice; addition 5.3 + 5.4 = 10.7 m; total 28.4 m = LiDAR eave. `height:max` 32.6 m = rooftop mechanical enclosures (2002 rooftop photo, 2025 ortho).

| Element | Material | Colour (hex, judge) | Conf. |
|---|---|---|---|
| Wall, storeys 1-4, all faces | precast concrete with exposed light aggregate; ~1.2 m piers at 7.9 m bay lines, projecting fins, flat recessed panels | base **#c2beb6** (Lab 77/0.3/4.6), diffuse #a8a49c, shade #8c8981; reads #e4dfd3 in full sun. vs `WALL` #d6cec2: lighter and yellower than reality | 0.85 |
| Structural bays | 7.9 m module: 11 on ESE and WNW (drawing + ortho teeth + fin fit), 6 on SSW and NNE | - | 0.90 long / 0.60 short |
| Windows, storeys 2-3, ESE | 6 evenly spaced tall windows per bay (0.75 x 3.3 m, pitch 1.3 m, 0.5 m fins), 66 per floor, transom ~1/3 down | glass #383836, frames dark-bronze #2f2a25 | 0.85 |
| Windows, storeys 2-3, SSW/NNE/WNW | 3 lights per bay: one ~0.6 m light + one ~0.7 m fin + ~1.3 m flat panel per 2.6 m; 33 (WNW) / 18 / 18 per floor; some louvred vents on WNW/NNE; storey-2 and -3 lights stacked with a 0.3 m spandrel | as above | 0.80 |
| Trim | oxblood bands: ~0.35 m under the storey-4 slab, continuous strip over the ground-floor storefront; red-brown sill panels in the bottom 20-25 % of every slit light **on the Freret (SSW) face only** (2007 and 2021; absent NNE 2019, WNW 2013/2018; ESE unseen) | **#5a4437**, shade #3a2c26 | 0.70 (sill panels 0.75) |
| Ground floor | ~1.0 m exposed-aggregate plinth/podium with planters; bronze-tinted storefront, ~5 lights (~1.5 m) per bay, recessed ~1.5 m behind piers under a dark soffit; entrance doors on ESE near the Freret corner with ramp + steps | glazing **#4f463a** (sun #756b52, shade #302a24), frames #2a2420; plinth #b3aca1 (shade #7a736a) | 0.80 / base 0.70 |
| Storey 4 (terrace) | continuous glazing 1.5-2 m behind a 1.0 m precast balustrade; roof slab projects ~1.5-2 m with a 0.7 m pale fascia, exposed beam ends, dark soffit - now the cornice under the addition | terrace glass #2e3238, fascia #bdb9b1, soffit #4a3f38 | 0.80 |
| Addition, storeys 5-6 | flat light silver-grey aluminium composite panels (joints ~1.0-1.2 m vertical, ~1.5 m horizontal), satin, sky-reflecting; set ~1.2 m inside the slab edge on WNW/SSW/NNE; flush thin coping, no parapet | panel **#c4cad1** (with a specular sky term; overcast #b3bcc5, sun #c1d3ea, sky-lit shade #98aac8); coping #cfd4da | 0.80 |
| Addition faces | ESE: 11-bay deep loggia (fins ~0.5 m x ~2.5 m deep reaching the slab edge). SSW: from the W corner 3-4 loggia-type recessed bays, short flat panel, group of 3-4 full-height slots, flat to the S corner. WNW: flat panel with 3 slots over ~2/3, then 3 recessed bays at the S end. NNE: flat panel with 3 slots. The SSW and WNW bays meet as a two-sided corner loggia at the W corner | loggia frame #e6e8ea (sky-lit #9aadcd), recess #24272c (shade #0c1019), loggia glass #2f3e39, slot glass #68717a | ESE 0.90, SSW 0.80, WNW 0.70, NNE 0.65, corner 0.70 |
| Roof | flat, white membrane largely covered by PV arrays + 3 mechanical enclosures (2025 ortho) - keep orthophoto colour | - | verified |

Render recommendations (judge): split the wall material at z = 17.7 m with a projecting pale cornice slab; lower block precast #c2beb6 with fin relief or a fin-shadow texture; ground floor 1 m plinth + dark bronze storefront recessed 1.5 m; oxblood bands all round, sill panels on Freret only; addition panel #c4cad1 with specular, set back 1.2 m, loggia bays as above.

### 6c. Two-pass agreement table (judge adjudication, authoritative)

| # | attribute | pass 1 | pass 2 | agree? | final (judge) | conf |
|---|---|---|---|---|---|---|
| 1 | wall material | exposed-aggregate precast, fins + flat panels, storeys 1-4 | same (buff-white matrix, grey-cream speckle) | yes | same; ~1.2 m piers at 7.9 m bay lines, fins, flat panels | 0.90 |
| 2 | wall colour | #c0bdb5 sunlit / #a5a097 diffuse / #8a8781 shade | #c2beb6 (albedo-calibrated vs white truck) / #9c9890 shade | yes | #c2beb6 base, #a8a49c diffuse, #8c8981 shade (judge: 2019 pier #a09b93, 2018 overcast #aeada6) | 0.85 |
| 3 | structural bays, long sides | 11 (7.9 m) | 11 (0.85) | yes | 11 @ 7.9 m (drawing + ortho teeth + fin fit) | 0.90 |
| 4 | structural bays, short sides | implied 6 (17 units / 3) | 6 (0.5) | mostly | 6 (2007 storefront: 5 lights per pier interval = ~7.5-7.9 m) | 0.60 |
| 5 | window rhythm, ESE face | 3 units/bay, pitch 2.6 m, 0.85 m wide, 33/side | 6 windows/bay, pitch 1.3 m, 0.75 m, 66/floor | NO | pass 2: 6 evenly spaced 0.75 m windows per bay with 0.5 m fins, 66 per floor (drawing 6x + Feb-2026 4x) | 0.85 |
| 6 | window rhythm, SSW/NNE/WNW | 3 units/bay, pitch 2.6 m, 0.85 m, 33 long / 17 short | 3 PAIRS of 0.4 m lights (6/bay), 66 long / 36 short | NO | pass 1's rhythm: ONE ~0.6 m light + ONE ~0.7 m fin + ~1.3 m flat panel per 2.6 m; 33 / 18 / 18 (2007 3.4x zoom shows light+fin, not a pair; Zimple WNW row counts ~33) | 0.80 |
| 7 | red-brown sill panels | none after 2013-14 reglazing | present on SSW (Nov 2021), absent NNE/WNW | NO | pass 2: SSW (Freret) only; absent NNE 2019, WNW 2013/2018; ESE not seen | 0.75 |
| 8 | trim (oxblood) colour | #4a3028 (shade sample) | #5b4538 / #3a2c26 | minor | #5a4437 base, #3a2c26 shade | 0.70 |
| 9 | upper glazing tint | #353639 | #3a3936 | yes | #383836, transom 1/3 down | 0.75 |
| 10 | window frame | #1a1a14 (clipped 2001 sample) | #2f2a25 dark bronze | minor | #2f2a25 dark-bronze anodised | 0.70 |
| 11 | ground-floor storefront | #312a25 (deep-shade sample) | #5a4f3d (sun-based) | minor | #4f463a mid (judge: sun #70684f-#796f55, shade #302a24), 5 lights per bay, recessed 1.5 m | 0.80 |
| 12 | base / plinth | #a9a49c, 1.1 m | #b7ada0, 1.0 m | yes | #b3aca1, 1.0 m, coarser aggregate, planters, ramp at ESE entrance | 0.70 |
| 13 | original roof slab / cornice | 17.5 m, fascia #bdb9b0, 2 m overhang | 17.7 m, #bdb9b1, 1.5-2 m | yes | 17.7 m, #bdb9b1, soffit #4a3f38 | 0.80 |
| 14 | pass-1 'roof fascia sunlit #766254 reliable' | fascia | mis-hit (shaded band) | NO | pass 2: judge re-measured same zone #7d695b = shaded band; fascia is #bdb9b1 | 0.90 |
| 15 | addition present, 2 storeys (5-6), 2014-16 | yes | yes | yes | yes | 0.95 |
| 16 | addition panel colour | #b4bec6 base (blue-grey), sun #c0d3e9 | #c8cdd3 neutral + specular | minor | #c4cad1 with specular sky term; overcast #b3bcc5, sun #c1d3ea, low-sun reflection can reach #6fa4e7 | 0.80 |
| 17 | addition ESE loggia | 11 bays, white fins, black recess | 11 bays | yes | 11 bays; frame #e6e8ea, recess #24272c, glass #2f3e39 | 0.90 |
| 18 | addition SSW (Freret) face | flat + 4-5 slots; 'other three edges plain, settled by ortho' (0.85) | flat + 4 slots + 2-3 recessed bays at W end (0.5) | NO | pass 2, strengthened: 3-4 deep recessed bays at W end, short flat, group of 3-4 slots, flat to S corner (Newcomb_Blvd_18 roofline continuous across bays+panel and 6+ ESE bays to its right; April_2019_05; pic_3). Ortho cannot see recesses under a continuous fascia | 0.80 |
| 19 | addition WNW (Audubon) face | flat + slots | flat + 2-3 slots | partial | NEITHER: flat panel with 3 slots over N ~2/3 + 3 recessed loggia-type bays at the S (Freret) end (Zimple_2018, N end nearer) | 0.70 |
| 20 | addition NNE face | 3-5 slots (from photos 64/66) | unverified | partial | flat panel, 3 slots, flat N corner (2019 portrait relabelled NNE + Zimple_2018 grazing left face); possible recess at E corner unverified | 0.65 |
| 21 | W corner of addition | plain | (implied) | - | two-sided corner loggia: ~3 WNW bays + 3-4 SSW bays meet at the Freret/Audubon corner | 0.70 |
| 22 | face label: Zimple_Street_2018 | NNE face | WNW face | NO | WNW (pass 2): 11-bay long face, NNE grazing at left, bays narrow toward S | 0.85 |
| 23 | face label: 29-Mar-2019 portrait | NNE from NW corner | WNW from N end | NO | NNE face seen from its E end looking WNW (pass 1's face, neither viewpoint): ~18-21 lights not 33, flat far corner (WNW S end has bays), Dixon-Hall-side brick wall at right, grey-green metal-roofed chapel beyond far corner, sun az 121 behind camera | 0.75 |
| 24 | storey heights | 4.3/4/4/4/5.5/5.5 = 27.3 m | 4.8/4/4/4.2(+0.7 slab)/5.3/5.4 = 28.4 m | minor | pass 2 (sums to LiDAR 28.4) | 0.55 |
| 25 | addition setback ~1.2 m on 3 sides, loggia to slab edge | yes | yes | yes | yes (explains small roofline jog at bay/panel junctions) | 0.80 |
| 26 | entrance ESE near Freret corner, planters, iron fence, PV roof, 3 rooftop enclosures | yes | yes | yes | yes | 0.70 |

Lessons the PoC produced (judge/skeptic-confirmed): ground photos alone gave contradictory addition layouts and two mislabelled faces; the ortho's roof "teeth" are relief displacement of one wall and cannot exclude recesses under a continuous fascia; fin shadows are easily counted as a second window; Stern Hall look-alikes must be triaged by facade pattern; sunlit samples carry warm sun + blue sky fill, so the even-light 2019 portrait was the best neutral reference; pass-1 mislabelled a shaded band as the pale fascia.

### 6d. What stayed uncertain (judge's open questions)

1. Count of recessed loggia-type bays at the W corner (3 or 4 on SSW, 3 on WNW) and their module (7.9 m or narrower); whether they form one continuous corner loggia.
2. Whether the NNE addition face has a recessed bay at its E corner next to the ESE loggia.
3. Slot counts and positions: Freret 3 or 4; WNW 3 (or 4); NNE 3 - no frontal NNE photo exists.
4. Red-brown sill panels on the ESE face (never checked at close range).
5. Terrace-floor (storey 4) column spacing on ESE (bay lines vs intermediate columns).
6. Short sides: 6 equal bays (~7.7 m) or 5 full bays plus narrower end bays.
7. Ground-floor storefront lights per bay: 5 (Freret 2007) vs 7-8 (ESE drawing).
8. Exact position of the ESE entrance doors and whether a second entrance exists on Freret.
9. Slit light width: 0.6 m (judge) vs 0.85 (pass 1) vs 0.4 (pass 2) - needs a scaled measurement.
10. Dec-2014 weather-barrier openings covered the S half of the WNW face, more than the 3 bays seen in 2018.
11. Whether the 2016 Mapillary Freret sequence (needs a token) contains a frontal Freret view.

What would raise confidence: a frontal NNE photo from the Dixon Hall / Commons side; a view of the SW corner from Audubon St; a clean frontal across Freret without oaks; a straight-on close-up of one bay per face with a scale reference; slicing the QL1 wall points at 17.7 m for the slab and the setback; one overcast photo with a grey card. A 30-minute site walk would settle every layout item.

---

## 7. Refuted findings

| Lane / finding | Skeptic's reason (condensed) |
|---|---|
| extraction-methods: "Window-grid regularity from one oblique photo: rectify -> detect -> cluster -> period; extrapolate with LiDAR facade length" | Two of three citations are wrong (ISPRS Annals II-5/W2 2013 is the Laser Scanning workshop with no Wenzel/Foerstner paper - the real one is Wenzel, Drauschke & Foerstner, PRIA 18(3) 2008; arXiv 2008.01286 is a Photo2Building cloud-deployment paper with no lattice model); GATA2Floor is quoted as "collapses without rectification" but runs no rectified-vs-unrectified ablation; the "~5 %" accuracy has no source; a two-vanishing-point fronto-parallel homography needs the focal length, which is unrecoverable on level-camera photos (HT 2026 photo: vertical VP at ~infinity, f^2 < 0, VP directions 76-78 deg apart for any plausible f, 13.5 deg residual shear), and Commons photos are cropped so EXIF principal points are unreliable; the focal-free affine rectification works but leaves the aspect ratio free, so a single metres/px from "LiDAR height / storey count" cannot be applied horizontally (storeys are non-uniform on HT anyway); HT has four horizontal zones, not "two grids"; the "Claude boxes <= 40 windows" threshold is unsourced and untestable (401 key). Replacement rule: section 3d. |
| apply-to-model (b): "Procedural facade in the page works with no per-building textures and no new GLB attributes ... proven by headless render" | The shader mechanism is correct for three.js r128 and compiles under SwiftShader, but the PoC's embedded GLB is a float32, unquantized 3,013-vertex mesh from the un-integrated `decimate_keep_walls` prototype, not a `pack_web.py` product. The shipped HT mesh (2,717 verts, 3 vertical faces, 90 % of non-roof area in tilted slivers) fails the hook's `wallness > 0.9` gate: rendering the same hook on it yields a floating roof with a few painted slivers; across all 88 shipped meshes only 18.1 % of non-roof area passes (house chunks 4.9-34 %). So the finding as scoped ("template-only, 0 bytes shipped, ~120 lines") omits a hard prerequisite - the pack_web cap-before-decimate change - and the merged-house attribute variant has no source for per-building phi/base (`ranges` = `[offset,count,fit]`; with 3 surviving bottom vertices a load-time MABR gives 145 deg vs the true 106 deg). Re-filed as step 3 of section 4b, dependent on step 1. |
| apply-to-model (c): "Roof colours are already the right source and cross-check cleanly for Howard-Tilton; flatten shadowed roof pixels on single-plane roofs" | The quoted HT roof colours (main [186,180,160], unit [118,125,118], p20 [107,115,106]) match only the superseded `out/core`, `core2`, `core3` builds (20:44-20:50, coloured from the old NAIP PNG; `data/ortho2025.png` was created at 23:50); the current 2025-ortho builds give a neutral membrane [183,186,180] and pale units [173,185,183]. The dark 27.5 % of roof vertices are five PV arrays (blue-shifted, exactly matching the ortho crop), not baked shadow - `data/facades/howard_tilton.json` already says so. The proposed cleanup (`roof:planes == 1 & fit:rmse < 0.1` -> plane median) would erase the PV arrays on the PoC building itself, the packer has no per-plane assignment to use, and the rule reaches 3.4 % (core_v2) to 6.3 % (full) of buildings, not "~85 %" (that is the share with >= 1 plane). The sound parts (roofs keep ortho colour, spec never touches roofs, fix the wall-top leak by a vertex split) are kept as the roof rule in section 4b. |

Corrections applied to surviving findings (not refuted, but the doc uses the corrected numbers): Commons downloads are 1920 px; cityscapes subcat has 46 files; Mapillary creators are three accounts and campus totals are 16,215 images; the address-chain recipe's `gsradius=80` and Mapillary bbox were too small and its Flickr call lacked a limiting agent; Concept3D image count is 284 (not 289) and the map's footer does link terms; the storey-height band 3.3-4.2 m is wrong; the "10,190 / 1,773 quads" counts do not match any build (22,628 / 1,941 for out/core); the "+0.61 MB" cap-fix cost is actually a reduction; `--decimate-named 0` costs +2.31 MiB; the page was packed from out/core_v2; the two 2001/2002 "stale" photos are pre-2015/16, not "pre-2014".

---

## 8. Next steps to scale

Before any new building: fix the API key (or install the `ant` CLI and `unset ANTHROPIC_API_KEY` so a profile can be used), `pip install anthropic` in `.venv`, register a Mapillary client token, land the `pack_web.py` cap-then-strip decimation (section 4b step 1) and repack from `out/core_v2` so walls exist to paint, and pick one facade-spec shape (section 3e). Then run the automated stages on Howard-Tilton first and diff against the hand-made spec - that is the only calibration point the pipeline has.

### The next 10 buildings

Selection rule: named OSM footprint with LiDAR fit in `out/tulane_enriched.geojson` (heights/levels below read from that file), a rich Commons category (verified counts) and Concept3D images (counts from the lane's dump; the starred ones were verified by the skeptic), and together they exercise every path the method has to handle: the Wikidata route, the alias table, brick vs concrete vs glass, a domed roof with no plane fit, and the Stern-Hall look-alike trap.

| # | Building (OSM name) | LiDAR h / OSM levels | Commons category (files) | Concept3D images | Why |
|---|---|---|---|---|---|
| 1 | Gibson Hall | 21.9 m / 4 | Gibson Hall, Tulane (53) | 12* | richest photo set; St Charles frontage; 1894 Richardsonian Romanesque stone + brick - first non-concrete material; Wikidata Q5559347 exists but is not in OSM (tests the `wbsearchentities` disambiguation against the London Gibson Hall) |
| 2 | Dinwiddie Hall | 20.3 m / 4 | Dinwiddie Hall (27) | 11* | brick/stone twin of Gibson on the St Charles front; 3 roof planes (pitched roof case) |
| 3 | Tilton Memorial Hall | 18.1 m / - | Tilton Hall, Tulane (12) | 10* | needs the alias (Tilton Hall = Tilton Memorial Hall) and is a name-collision trap with Howard-Tilton in Concept3D; description carries architects/year (1902, Andry & Bendernagel) |
| 4 | Percival Stern Hall | 22.2 m / 4 | Percival Stern Hall (22) | 11* | concrete pilotis + slit windows - the look-alike that contaminated the HT search; tests triage-by-pattern |
| 5 | Richardson Memorial Hall | 26.2 m / - | Richardson Memorial Hall, Tulane (7) | 13* | Concept3D-heavy / Commons-light case; `building=university` typology |
| 6 | Fogelman Arena (Devlin Fieldhouse) | 16.9 m / - | Devlin Fieldhouse (25) | 7 | one of only 3 other buildings with an OSM `wikidata` + P18 (Q5267618): exercises the Wikidata route end to end; alias Devlin = Fogelman |
| 7 | McAlister Auditorium | 19.2 m / - | McAlister Auditorium, Tulane University (27) | 3 | `roof:planes 0` (dome) - the roof-edge / non-planar case; 27 photos |
| 8 | Joseph Merrick Jones Hall | 17.0 m / 3 | Jones Hall, Tulane (21) | 4 | alias needed (Jones Hall); brick with limestone trim; OSM levels present |
| 9 | Lavin-Bernick University Center (LBC) | 13.6 m / - | Lavin-Bernick Center for University Life (49) | 5 | second-richest Commons set; glass + screen facade (glazing-dominant material) |
| 10 | Dixon Hall + Dixon Performing Arts Center | 12.3 / 11.4 m / - | Dixon Hall, Tulane (41) | 5 | two OSM footprints share one Commons category - tests photo-to-footprint assignment (Concept3D point-in-polygon) |

Reserves with the same criteria: Reily Student Recreation Center (34 / 4), Newcomb Hall (18 / 7), Stanley Thomas Hall (9 / 10*, levels 4), Boggs Center (6 / 12*, levels 6, 36.6 m), Hebert Hall (7 / 12*), Yulman Stadium (16 / 8*, Q8060993), Turchin Stadium (14 / 10*, Q5605129). Residence halls (Buddig 35.7 m / 12 levels, Monroe 41.8 m) have no Commons category and only the typology fallback until Concept3D `catId 18317` is fetched.

After those ten: build the hand alias table for the remaining ~30 named buildings that have a Commons subcategory, fetch Concept3D residence halls, and let everything else (2,486 unnamed footprints in the page) take the typology defaults with Mapillary 2016 plinth frames where a street-facing house needs a check.
