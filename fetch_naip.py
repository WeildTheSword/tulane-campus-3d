#!/usr/bin/env python3
"""Download a public-domain aerial orthophoto of the bbox from an ArcGIS ImageServer -> data/naip.png (+ .json sidecar)

Default source: USGS NAIPPlus (USDA NAIP, 0.3 m). --service points at any other exportImage endpoint (e.g. the LaDOTD 2025
0.15 m RGBI service); --bands picks bands (e.g. '3' = NAIP near-infrared -> a single-band PNG for NDVI).

Tiles are requested in UTM 15N (EPSG:26915) on an exact pixel grid. Requesting in lon/lat makes the server pad the latitude
span to keep its pixel aspect (measured +7.7 %), which duplicated a strip of ground at every tile seam. The sidecar records
the UTM extent (`bbox_utm`) that build_model.py samples against, plus the lon/lat envelope for reference."""
import argparse, io, json, math, os, sys, requests
from PIL import Image
from pyproj import Transformer
ap = argparse.ArgumentParser(); ap.add_argument('--bbox', default='-90.1290,29.9330,-90.1120,29.9500', help='minLon,minLat,maxLon,maxLat')
ap.add_argument('--gsd', type=float, default=0.3, help='ground sample distance in metres per pixel (NAIPPlus native 0.3; LaDOTD 2025 native 0.15)')
ap.add_argument('--tile', type=int, default=3000, help='max pixels per request edge (service limits are 4000-4100)'); ap.add_argument('--out', default='data/naip.png')
ap.add_argument('--bands', default=None, help="ImageServer bandIds, e.g. '3' for the near-infrared band (R,G,B,NIR = 0,1,2,3); default = natural colour")
ap.add_argument('--service', default=None, help='ArcGIS ImageServer exportImage URL to use instead of the USGS NAIP services')
ap.add_argument('--license', default=None, help='licence note to store with --service'); a = ap.parse_args()
EPSG = 26915
bbox = [float(v) for v in a.bbox.split(',')]; lon0, lat0, lon1, lat1 = bbox
tr = Transformer.from_crs(4326, EPSG, always_xy=True); inv = Transformer.from_crs(EPSG, 4326, always_xy=True)
cx = [lon0, lon1, lon1, lon0]; cy = [lat0, lat0, lat1, lat1]; E, N = tr.transform(cx, cy)
x0, x1, y0, y1 = math.floor(min(E)), math.ceil(max(E)), math.floor(min(N)), math.ceil(max(N))          # UTM envelope of the lon/lat bbox, whole metres
W = int(round((x1 - x0) / a.gsd)); H = int(round((y1 - y0) / a.gsd)); x1 = x0 + W * a.gsd; y1 = y0 + H * a.gsd   # exact grid
nx, ny = math.ceil(W / a.tile), math.ceil(H / a.tile)
services = [('https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage', 'USDA NAIP, public domain'),
            ('https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export', 'USGS Imagery Only basemap, public domain')]
if a.service: services = [(a.service, a.license or 'see service metadata')]
HEADERS = {'User-Agent': 'tulane-campus-3d/1.0'}
mode = 'L' if a.bands and ',' not in a.bands else 'RGB'

def fetch_tile(url, tb, tw, th):
    params = {'bbox': ','.join(f'{v:.3f}' for v in tb), 'bboxSR': EPSG, 'imageSR': EPSG, 'size': f'{tw},{th}', 'format': 'png', 'f': 'json'}
    if a.bands: params['bandIds'] = a.bands
    meta = requests.get(url, params=params, headers=HEADERS, timeout=300).json(); e = meta.get('extent') or {}
    if 'error' in meta: raise RuntimeError(meta['error'])
    if any(abs(e.get(k, 1e9) - v) > 0.01 for k, v in zip(('xmin', 'ymin', 'xmax', 'ymax'), tb)) or (meta.get('width'), meta.get('height')) != (tw, th):
        raise RuntimeError(f'server changed the tile extent: asked {tb} {tw}x{th}, got {e} {meta.get("width")}x{meta.get("height")}')
    params['f'] = 'image'; r = requests.get(url, params=params, headers=HEADERS, timeout=300)
    if not r.ok or not r.content.startswith(b'\x89PNG'): raise RuntimeError(f'{r.status_code}: {r.content[:120]!r}')
    return Image.open(io.BytesIO(r.content)).convert(mode)

for url, lic in services:
    try:
        mosaic = Image.new(mode, (W, H))
        for j in range(ny):          # rows, top (max N) to bottom
            for i in range(nx):
                px0, px1 = i * a.tile, min((i + 1) * a.tile, W); py0, py1 = j * a.tile, min((j + 1) * a.tile, H)
                tb = [x0 + px0 * a.gsd, y1 - py1 * a.gsd, x0 + px1 * a.gsd, y1 - py0 * a.gsd]
                mosaic.paste(fetch_tile(url, tb, px1 - px0, py1 - py0), (px0, py0)); print(f'  tile {j * nx + i + 1}/{nx * ny} ok', flush=True)
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True); mosaic.save(a.out, optimize=True)
        lons, lats = inv.transform([x0, x1, x1, x0], [y0, y0, y1, y1])
        json.dump({'crs': f'EPSG:{EPSG}', 'bbox_utm': [x0, y0, x1, y1], 'bbox': [min(lons), min(lats), max(lons), max(lats)], 'bbox_requested': bbox,
                   'size': [W, H], 'gsd_m': a.gsd, 'source': url, 'license': lic, 'bands': a.bands or 'RGB'}, open(os.path.splitext(a.out)[0] + '.json', 'w'))
        print(f'saved {a.out} {W}x{H} px ({a.gsd} m/px, EPSG:{EPSG} {x0:.0f},{y0:.0f}..{x1:.0f},{y1:.0f}), {os.path.getsize(a.out) // 1024} KB from {url}'); sys.exit(0)
    except Exception as e: print('failed', url, e)
sys.exit('could not fetch imagery; the model still builds without it (untextured terrain)')
