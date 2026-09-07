#!/usr/bin/env python3
"""Download OpenStreetMap footprints, streets, streetcar line, trees and parks for the bbox -> data/osm.geojson"""
import argparse, json, os, sys, time, requests, osm2geojson
ap = argparse.ArgumentParser(); ap.add_argument('--bbox', default='29.9330,-90.1290,29.9500,-90.1120', help='south,west,north,east'); ap.add_argument('--out', default='data/osm.geojson'); a = ap.parse_args()
b = a.bbox
q = f'''[out:json][timeout:180];
( way["building"]({b}); relation["building"]({b}); way["highway"]({b}); way["railway"="tram"]({b}); node["natural"="tree"]({b});
  way["leisure"]({b}); way["landuse"="grass"]({b}); way["amenity"="parking"]({b}); way["natural"="water"]({b}); );
out body; >; out skel qt;'''
HEADERS = {'User-Agent': 'tulane-campus-3d/1.0 (https://github.com/tulane-campus-3d)'}  # overpass-api.de answers 406 without a UA
for url in ['https://overpass-api.de/api/interpreter', 'https://overpass.osm.ch/api/interpreter', 'https://maps.mail.ru/osm/tools/overpass/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']:
    try:
        r = requests.post(url, data={'data': q}, headers=HEADERS, timeout=300); r.raise_for_status(); data = r.json(); break
    except Exception as e:
        print('overpass mirror failed:', url, e); time.sleep(3)
else:
    sys.exit('Overpass unavailable — retry later, or export GeoJSON from overpass-turbo.eu and save it as data/osm.geojson')
geo = osm2geojson.json2geojson(data)
os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True); json.dump(geo, open(a.out, 'w'))
n = sum(1 for f in geo['features'] if (f['properties'].get('tags') or {}).get('building'))
print(f"saved {a.out}: {len(geo['features'])} features, {n} buildings")
