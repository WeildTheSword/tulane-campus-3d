#!/usr/bin/env bash
# One-shot pipeline: real footprints + USGS LiDAR + NAIP -> game-ready glTF. Run inside a GitHub Codespace or any terminal with Python 3.10+.
set -e
pip install -r requirements.txt
python fetch_osm.py                 # footprints, streets, streetcar line, trees, parks
python fetch_naip.py                # aerial orthophoto for the texture
python fetch_lidar.py --yes         # the laser scan (several hundred MB; skip this line to build from tags only)
python build_model.py --align-st-charles --surface
echo "Outputs are in ./out — open the .glb files in Blender/Unity/Godot/Unreal, or load out/tulane_enriched.geojson into tulane_voxel_campus.html"
