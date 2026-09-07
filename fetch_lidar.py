#!/usr/bin/env python3
"""Find and download USGS 3DEP LiDAR point-cloud tiles (public domain) covering the bbox -> data/lidar/*.laz
Uses The National Map access API. Tiles are ~100-400 MB each; a campus bbox usually needs 2-6 tiles."""
import argparse, os, sys, requests
ap = argparse.ArgumentParser(); ap.add_argument('--bbox', default='-90.1290,29.9330,-90.1120,29.9500', help='minLon,minLat,maxLon,maxLat')
ap.add_argument('--out', default='data/lidar'); ap.add_argument('--project', default=None, help='only tiles whose title contains this text'); ap.add_argument('--list', action='store_true'); ap.add_argument('--yes', action='store_true'); a = ap.parse_args()
API = 'https://tnmaccess.nationalmap.gov/api/v1/products'
r = requests.get(API, params={'datasets': 'Lidar Point Cloud (LPC)', 'bbox': a.bbox, 'prodFormats': 'LAZ', 'outputFormat': 'JSON', 'max': 500}, timeout=180); r.raise_for_status()
items = r.json().get('items', [])
if a.project: items = [i for i in items if a.project.lower() in (i.get('title') or '').lower()]
if not items: sys.exit('no LiDAR tiles returned for this bbox — try https://apps.nationalmap.gov/downloader/ (Elevation Source Data) or Louisiana\'s atlas.ga.lsu.edu')
proj = {}
def project_of(item):  # title looks like 'USGS Lidar Point Cloud LA_2021GreaterNewOrleans_C22 w0777n3314' -> the project id is the 5th word
    w = (item.get('title') or '?').split(' '); return w[4] if len(w) > 4 else w[0]
for i in items: proj.setdefault(project_of(i), []).append(i)
print(f'{len(items)} tiles from {len(proj)} project(s):')
for k, v in proj.items(): print(f'  {k}: {len(v)} tiles, published {v[0].get("publicationDate")}, {sum((i.get("sizeInBytes") or 0) for i in v) / 1e6:.0f} MB, e.g. {v[0].get("title")}')
if a.list: sys.exit(0)
newest = max(proj.values(), key=lambda v: str(v[0].get('publicationDate')))
if not a.project and len(proj) > 1: print('downloading the newest project only (use --project to pick another)'); items = newest
total = sum((i.get('sizeInBytes') or 0) for i in items)
if not a.yes and input(f'download {len(items)} tiles ({total / 1e6:.0f} MB)? [y/N] ').lower() != 'y': sys.exit(0)
os.makedirs(a.out, exist_ok=True)
for i in items:
    url = i['downloadURL']; fn = os.path.join(a.out, os.path.basename(url.split('?')[0]))
    if os.path.exists(fn): print('have', fn); continue
    print('downloading', fn)
    with requests.get(url, stream=True, timeout=600) as s:
        s.raise_for_status()
        with open(fn + '.part', 'wb') as f:
            for chunk in s.iter_content(1 << 20): f.write(chunk)
    os.rename(fn + '.part', fn)
print('done')
