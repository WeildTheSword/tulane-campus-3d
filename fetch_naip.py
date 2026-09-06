#!/usr/bin/env python3
"""Download a public-domain USDA NAIP aerial orthophoto of the bbox from USGS -> data/naip.png (+ .json with the bbox)"""
import argparse, json, os, sys, requests
ap = argparse.ArgumentParser(); ap.add_argument('--bbox', default='-90.1290,29.9330,-90.1120,29.9500', help='minLon,minLat,maxLon,maxLat'); ap.add_argument('--size', type=int, default=4096); ap.add_argument('--out', default='data/naip.png'); a = ap.parse_args()
bbox = [float(v) for v in a.bbox.split(',')]
services = ['https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage',
            'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export']
for url in services:
    try:
        r = requests.get(url, params={'bbox': a.bbox, 'bboxSR': 4326, 'imageSR': 4326, 'size': f'{a.size},{a.size}', 'format': 'png', 'f': 'image'}, timeout=300)
        if r.ok and r.headers.get('content-type', '').startswith('image'):
            os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True); open(a.out, 'wb').write(r.content)
            json.dump({'bbox': bbox, 'size': [a.size, a.size], 'source': url, 'license': 'USDA NAIP, public domain'}, open(os.path.splitext(a.out)[0] + '.json', 'w'))
            print('saved', a.out, len(r.content) // 1024, 'KB from', url); sys.exit(0)
        print('no image from', url, r.status_code)
    except Exception as e: print('failed', url, e)
sys.exit('could not fetch imagery; the model still builds without it (untextured terrain)')
