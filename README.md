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
   python fetch_osm.py && python fetch_naip.py
   python fetch_lidar.py --list        # see which scans cover the campus
   python fetch_lidar.py --yes         # download the newest one (a few hundred MB)
   python build_model.py --align-st-charles --surface --res 0.5 --obj
   ```

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

## Making it more photoreal

- Stream Google's Photorealistic 3D Tiles with Cesium for Unity/Unreal for live photogrammetry (API key + attribution; can't be baked into a build).
- Scan hero buildings on site with Polycam / Scaniverse / RealityScan and swap them in.

## Accuracy notes

Footprints are survey-grade; heights and roofs are measured from the scan (typically ±0.3 m). Buildings newer than the scan flight (check the project date in `fetch_lidar.py --list`) fall back to OSM tags or estimates and are flagged with `height:source` in `tulane_enriched.geojson`. Missing or outdated outlines are best fixed at openstreetmap.org, then re-run `fetch_osm.py`.
