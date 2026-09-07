#!/usr/bin/env python3
"""Download the City of New Orleans building footprints (Enterprise GIS, updated quarterly) for the bbox -> data/city_footprints.geojson
Used by build_model.py --extra-footprints to add buildings OSM lacks and to decide, with the scan, which OSM buildings are gone."""
import argparse, json, os, requests
ap = argparse.ArgumentParser(); ap.add_argument('--bbox', default='-90.1290,29.9330,-90.1120,29.9500', help='minLon,minLat,maxLon,maxLat'); ap.add_argument('--out', default='data/city_footprints.geojson'); a = ap.parse_args()
b = [float(v) for v in a.bbox.split(',')]
r = requests.get('https://data.nola.gov/resource/prh5-qsuf.geojson', params={'$where': f'within_box(the_geom, {b[3]}, {b[0]}, {b[1]}, {b[2]})', '$limit': 100000}, headers={'User-Agent': 'tulane-campus-3d/1.0'}, timeout=600)
r.raise_for_status(); gj = r.json()
os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True); json.dump(gj, open(a.out, 'w'))
print(f"saved {a.out}: {len(gj.get('features', []))} footprints (City of New Orleans Building Footprint, data.nola.gov prh5-qsuf, public)")
