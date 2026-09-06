#!/usr/bin/env python3
"""
build_model.py — turn real survey data into a game-ready 3D model of the Tulane uptown campus.

Inputs (all free / public):
  * data/osm.geojson        OSM building footprints, streets etc. (fetch_osm.py) — or an Overture buildings GeoJSON
  * data/lidar/*.laz        USGS 3DEP LiDAR point clouds (fetch_lidar.py)  [optional but this is the "scan"]
  * data/naip.png + .json   NAIP aerial orthophoto of the bbox (fetch_naip.py) [optional, used as texture/colors]

Outputs (out/):
  tulane_buildings.glb      one mesh per building; walls at LiDAR-measured height, roof surface from the LiDAR DSM
  tulane_terrain.glb        ground surface from the LiDAR ground returns, textured with the orthophoto
  tulane_trees.glb + .json  tree instances detected from the LiDAR canopy (position, height, crown radius)
  tulane_scan_surface.glb   optional (--surface): the raw scanned surface (ground+buildings+trees) as one textured mesh
  tulane_enriched.geojson   the footprints with measured `height`, `roof:height` etc. — loads straight into the voxel viewer
  preview_dsm.png           hillshaded scan with footprints, for a sanity check

Coordinate frame: meters, Y up, X east, Z south (glTF convention). Optional --align-st-charles rotates so
St. Charles Avenue runs along +X (the same frame the voxel viewer uses).
"""
import argparse, glob, json, math, os, sys, time
import numpy as np

def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)

# ----------------------------------------------------------------------------- args
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--osm', default='data/osm.geojson', help='GeoJSON with building footprints (OSM via osm2geojson, Overpass Turbo export, or Overture)')
ap.add_argument('--lidar', default='data/lidar', help='directory of .laz/.las files, or a single file')
ap.add_argument('--naip', default='data/naip.png', help='orthophoto PNG (with a sidecar .json holding its lon/lat bbox)')
ap.add_argument('--bbox', default=None, help='minLon,minLat,maxLon,maxLat (default: bbox of the footprint data)')
ap.add_argument('--out', default='out')
ap.add_argument('--res', type=float, default=1.0, help='roof/DSM grid resolution in m (0.5 for finer roofs)')
ap.add_argument('--terrain-res', type=float, default=2.0, help='terrain grid resolution in m')
ap.add_argument('--surface', action='store_true', help='also export the whole scanned surface as one mesh')
ap.add_argument('--surface-res', type=float, default=2.0)
ap.add_argument('--align-st-charles', action='store_true', help='rotate the frame so St. Charles Ave runs along +X')
ap.add_argument('--lidar-epsg', type=int, default=None, help='override the point cloud CRS if the files lack one')
ap.add_argument('--z-scale', type=float, default=None, help='multiply LiDAR z by this (0.3048 if elevations are in feet); auto by default')
ap.add_argument('--max-points', type=int, default=60_000_000, help='random-subsample the cloud above this many points')
ap.add_argument('--max-trees', type=int, default=6000)
ap.add_argument('--obj', action='store_true', help='also write .obj copies of the glb files')
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

from pyproj import Transformer, CRS
import shapely
from shapely.geometry import shape, Polygon, MultiPolygon
from scipy import ndimage
import trimesh

# ----------------------------------------------------------------------------- footprints
def load_geojson(path):
    with open(path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    feats = gj['features'] if gj.get('type') == 'FeatureCollection' else [gj]
    return [f for f in feats if f.get('geometry')]

def props_of(f):
    """Normalize OSM (Overpass Turbo / osm2geojson) and Overture properties into one dict."""
    p = f.get('properties') or {}
    t = p.get('tags') if isinstance(p.get('tags'), dict) else p
    name = t.get('name') or (p.get('names') or {}).get('primary') if isinstance(p.get('names'), dict) else t.get('name')
    building = t.get('building') or p.get('subtype') or p.get('class') or ('yes' if 'height' in p or 'num_floors' in p else None)
    height = t.get('height', p.get('height'))
    levels = t.get('building:levels', p.get('num_floors'))
    fid = p.get('id') or p.get('@id') or f.get('id')
    return dict(name=name, building=building, height=_num(height), levels=_num(levels),
                roof_shape=t.get('roof:shape') or p.get('roof_shape'), tags=t, id=fid)

def _num(v):
    if v is None: return None
    try:
        return float(str(v).replace('m', '').replace(',', '.').strip().split(' ')[0])
    except Exception:
        return None

feats = load_geojson(args.osm)
log(f'{len(feats)} features in {args.osm}')

def walk(coords, fn):
    if isinstance(coords[0], (int, float)): fn(coords)
    else:
        for c in coords: walk(c, fn)

if args.bbox:
    minLon, minLat, maxLon, maxLat = [float(v) for v in args.bbox.split(',')]
else:
    lons, lats = [], []
    for f in feats: walk(f['geometry']['coordinates'], lambda c: (lons.append(c[0]), lats.append(c[1])))
    minLon, maxLon, minLat, maxLat = min(lons), max(lons), min(lats), max(lats)
log(f'bbox lon {minLon:.5f}..{maxLon:.5f} lat {minLat:.5f}..{maxLat:.5f}')

# ----------------------------------------------------------------------------- local frame
class Frame:
    """Local metric frame: origin at the bbox center, +y north (or rotated), computed through UTM 15N."""
    def __init__(self, lon0, lat0, theta=math.pi / 2):
        self.utm = CRS.from_epsg(32615)
        self.fwd = Transformer.from_crs(CRS.from_epsg(4326), self.utm, always_xy=True)
        self.inv = Transformer.from_crs(self.utm, CRS.from_epsg(4326), always_xy=True)
        self.E0, self.N0 = self.fwd.transform(lon0, lat0)
        self.set_theta(theta)
    def set_theta(self, theta):
        self.theta = theta
        self.A = (math.sin(theta), math.cos(theta))      # unit vector of +x in (E,N)
        self.L = (-math.cos(theta), math.sin(theta))     # unit vector of +y in (E,N)
    def from_EN(self, E, N):
        dE, dN = np.asarray(E) - self.E0, np.asarray(N) - self.N0
        return dE * self.A[0] + dN * self.A[1], dE * self.L[0] + dN * self.L[1]
    def from_lonlat(self, lon, lat):
        E, N = self.fwd.transform(np.asarray(lon), np.asarray(lat))
        return self.from_EN(E, N)
    def to_lonlat(self, x, y):
        x, y = np.asarray(x), np.asarray(y)
        E = self.E0 + x * self.A[0] + y * self.L[0]
        N = self.N0 + x * self.A[1] + y * self.L[1]
        return self.inv.transform(E, N)

frame = Frame((minLon + maxLon) / 2, (minLat + maxLat) / 2)
if args.align_st_charles:
    best, theta = 0, None
    for f in feats:
        p = props_of(f); g = f['geometry']
        if g['type'] == 'LineString' and (p['tags'].get('highway') or p['tags'].get('railway')) and 'charles' in (p['tags'].get('name') or '').lower():
            c = g['coordinates']; E0, N0 = frame.fwd.transform(c[0][0], c[0][1]); E1, N1 = frame.fwd.transform(c[-1][0], c[-1][1])
            dE, dN = E1 - E0, N1 - N0; L = math.hypot(dE, dN)
            if L > best:
                best = L
                if dE < 0: dE, dN = -dE, -dN
                theta = math.atan2(dE, dN)
    if theta is not None:
        frame.set_theta(theta); log(f'aligned frame to St. Charles Avenue: bearing {math.degrees(theta):.1f} deg')
    else:
        log('no St. Charles Avenue way found; keeping north-up frame')

corners = np.array([frame.from_lonlat(lo, la) for lo, la in [(minLon, minLat), (maxLon, minLat), (maxLon, maxLat), (minLon, maxLat)]])
X0, X1 = corners[:, 0].min() - 20, corners[:, 0].max() + 20
Y0, Y1 = corners[:, 1].min() - 20, corners[:, 1].max() + 20
log(f'local extent x {X0:.0f}..{X1:.0f} m, y {Y0:.0f}..{Y1:.0f} m')

def to_export(V):
    """local (x east, y north, z up) -> glTF (x, y up, z south)"""
    return np.column_stack([V[:, 0], V[:, 2], -V[:, 1]])

# ----------------------------------------------------------------------------- orthophoto
naip = None
if os.path.exists(args.naip) and os.path.exists(os.path.splitext(args.naip)[0] + '.json'):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(args.naip).convert('RGB')
    meta = json.load(open(os.path.splitext(args.naip)[0] + '.json'))
    naip = dict(arr=np.asarray(img), bbox=meta['bbox'], img=img)
    log(f'orthophoto {img.size[0]}x{img.size[1]} px')

def sample_naip(x, y):
    if naip is None:
        return None
    lon, lat = frame.to_lonlat(x, y)
    b = naip['bbox']; H, W = naip['arr'].shape[:2]
    px = np.clip(((lon - b[0]) / (b[2] - b[0]) * W).astype(int), 0, W - 1)
    py = np.clip(((b[3] - lat) / (b[3] - b[1]) * H).astype(int), 0, H - 1)
    return naip['arr'][py, px]

def uv_naip(x, y):
    lon, lat = frame.to_lonlat(x, y); b = naip['bbox']
    return np.column_stack([(lon - b[0]) / (b[2] - b[0]), (lat - b[1]) / (b[3] - b[1])])

# ----------------------------------------------------------------------------- lidar
def read_lidar(path):
    import laspy
    files = sorted(glob.glob(os.path.join(path, '*.la[sz]'))) if os.path.isdir(path) else ([path] if os.path.exists(path) else [])
    if not files:
        return None
    xs, ys, zs, cs = [], [], [], []
    for fp in files:
        with laspy.open(fp) as f:
            crs = None
            try: crs = f.header.parse_crs()
            except Exception: pass
            if crs is None and args.lidar_epsg: crs = CRS.from_epsg(args.lidar_epsg)
            if crs is None:
                log(f'!! {os.path.basename(fp)}: no CRS in header; pass --lidar-epsg (e.g. 26915 for UTM15N m, 3452 for Louisiana South ftUS)'); continue
            hcrs = crs.sub_crs_list[0] if crs.is_compound else crs
            unit = (hcrs.axis_info[0].unit_name or '').lower()
            zscale = args.z_scale if args.z_scale else (0.3048006096 if 'foot' in unit or 'feet' in unit else 1.0)
            tr = Transformer.from_crs(hcrs, frame.utm, always_xy=True)
            n_keep = 0
            for chunk in f.chunk_iterator(3_000_000):
                E, N = tr.transform(np.asarray(chunk.x), np.asarray(chunk.y))
                x, y = frame.from_EN(E, N)
                keep = (x >= X0) & (x <= X1) & (y >= Y0) & (y <= Y1)
                if not keep.any(): continue
                xs.append(x[keep].astype(np.float32)); ys.append(y[keep].astype(np.float32))
                zs.append((np.asarray(chunk.z)[keep] * zscale).astype(np.float32))
                cs.append(np.asarray(chunk.classification)[keep].astype(np.uint8)); n_keep += int(keep.sum())
            log(f'{os.path.basename(fp)}: {f.header.point_count:,} pts, {n_keep:,} inside bbox, CRS {hcrs.name}, z x{zscale:g}')
    if not xs:
        return None
    x, y, z, c = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(cs)
    if len(x) > args.max_points:
        sel = np.random.default_rng(1).choice(len(x), args.max_points, replace=False)
        x, y, z, c = x[sel], y[sel], z[sel], c[sel]
    log(f'point cloud: {len(x):,} points; classes present: {sorted(set(np.unique(c).tolist()))}')
    return x, y, z, c

class Grid:
    def __init__(self, res):
        self.res = res; self.x0, self.y0 = X0, Y0
        self.nx = int(math.ceil((X1 - X0) / res)); self.ny = int(math.ceil((Y1 - Y0) / res))
    def idx(self, x, y):
        ix = np.floor((x - self.x0) / self.res).astype(np.int64); iy = np.floor((y - self.y0) / self.res).astype(np.int64)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return ix, iy, ok
    def max(self, x, y, z):
        ix, iy, ok = self.idx(x, y); out = np.full(self.nx * self.ny, -np.inf, np.float32)
        np.maximum.at(out, iy[ok] * self.nx + ix[ok], z[ok]); out[np.isinf(out)] = np.nan
        return out.reshape(self.ny, self.nx)
    def min(self, x, y, z):
        ix, iy, ok = self.idx(x, y); out = np.full(self.nx * self.ny, np.inf, np.float32)
        np.minimum.at(out, iy[ok] * self.nx + ix[ok], z[ok]); out[np.isinf(out)] = np.nan
        return out.reshape(self.ny, self.nx)
    def mean(self, x, y, z):
        ix, iy, ok = self.idx(x, y); s = np.zeros(self.nx * self.ny); n = np.zeros(self.nx * self.ny)
        np.add.at(s, iy[ok] * self.nx + ix[ok], z[ok].astype(np.float64)); np.add.at(n, iy[ok] * self.nx + ix[ok], 1)
        with np.errstate(invalid='ignore', divide='ignore'): m = s / n
        m[n == 0] = np.nan; return m.reshape(self.ny, self.nx)
    def count(self, x, y):
        ix, iy, ok = self.idx(x, y); n = np.zeros(self.nx * self.ny, np.int32); np.add.at(n, iy[ok] * self.nx + ix[ok], 1); return n.reshape(self.ny, self.nx)
    def centers(self, i0=0, i1=None, j0=0, j1=None):
        i1 = self.ny if i1 is None else i1; j1 = self.nx if j1 is None else j1
        cy, cx = np.mgrid[i0:i1, j0:j1]
        return self.x0 + (cx + 0.5) * self.res, self.y0 + (cy + 0.5) * self.res

def fill_nearest(a):
    m = np.isnan(a)
    if m.all(): return np.zeros_like(a)
    if not m.any(): return a
    idx = ndimage.distance_transform_edt(m, return_distances=False, return_indices=True)
    return a[tuple(idx)]

cloud = read_lidar(args.lidar)
G = Grid(args.res); GT = Grid(args.terrain_res)
if cloud is not None:
    x, y, z, c = cloud
    classified = bool(((c == 2) | (c == 6) | (c == 5)).any())
    good = ~np.isin(c, [7, 18])                                  # drop noise classes
    DSM = G.max(x[good], y[good], z[good])
    if classified and (c == 2).any():
        DTM = fill_nearest(GT.mean(x[c == 2], y[c == 2], z[c == 2])); DTM = ndimage.median_filter(DTM, 5)
    else:
        DTM = fill_nearest(GT.min(x[good], y[good], z[good])); DTM = ndimage.uniform_filter(ndimage.minimum_filter(DTM, 7), 7)
    DSM6 = G.max(x[c == 6], y[c == 6], z[c == 6]) if classified and (c == 6).any() else None
    VEG = G.count(x[np.isin(c, [3, 4, 5])], y[np.isin(c, [3, 4, 5])]) if classified else None
    BLD = G.count(x[c == 6], y[c == 6]) if classified else None
    log(f'DSM {G.nx}x{G.ny} @ {G.res} m, DTM {GT.nx}x{GT.ny} @ {GT.res} m, classified={classified}')
    zoom = (G.ny / GT.ny, G.nx / GT.nx)
    DTM_fine = ndimage.zoom(DTM, zoom, order=1)[:G.ny, :G.nx]
    if DTM_fine.shape != DSM.shape:
        DTM_fine = np.pad(DTM_fine, ((0, G.ny - DTM_fine.shape[0]), (0, G.nx - DTM_fine.shape[1])), mode='edge')
else:
    log('no LiDAR found — building LOD1 blocks from tags/estimates only (run fetch_lidar.py for the real scan)')
    DSM = DTM = DSM6 = VEG = BLD = None; classified = False
    DTM = np.zeros((GT.ny, GT.nx), np.float32); DTM_fine = np.zeros((G.ny, G.nx), np.float32)

# ----------------------------------------------------------------------------- mesh helpers
def heightfield_mesh(mask, top, base_z, x0, y0, res, walls=True):
    """Continuous surface over the cells in `mask` (corner heights = mean of adjacent cells), plus optional
    vertical walls down to base_z around the region. Returns (V local xyz, F, is_top per vertex)."""
    ny, nx = mask.shape
    tops = np.where(mask, top, np.nan).astype(np.float64)
    s = np.zeros((ny + 1, nx + 1)); n = np.zeros((ny + 1, nx + 1))
    val = np.nan_to_num(tops); cnt = (~np.isnan(tops)).astype(np.float64)
    for dy in (0, 1):
        for dx in (0, 1):
            s[dy:dy + ny, dx:dx + nx] += val; n[dy:dy + ny, dx:dx + nx] += cnt
    with np.errstate(invalid='ignore', divide='ignore'): H = s / n
    H = np.nan_to_num(H)
    cy, cx = np.mgrid[0:ny + 1, 0:nx + 1]
    V = np.column_stack([(x0 + cx * res).ravel(), (y0 + cy * res).ravel(), H.ravel()])
    vid = np.arange((ny + 1) * (nx + 1)).reshape(ny + 1, nx + 1)
    ci, cj = np.nonzero(mask)
    v00, v01, v11, v10 = vid[ci, cj], vid[ci, cj + 1], vid[ci + 1, cj + 1], vid[ci + 1, cj]
    F = [np.stack([v00, v01, v11], 1), np.stack([v00, v11, v10], 1)]
    is_top = np.ones(len(V), bool)
    if walls:
        pad = np.pad(mask, 1)
        extra_V, extra_F = [], []
        nv = len(V)
        # (neighbor offset, corner A, corner B) in CCW order around the cell
        for (di, dj), A, B in [((-1, 0), (0, 0), (0, 1)), ((0, 1), (0, 1), (1, 1)), ((1, 0), (1, 1), (1, 0)), ((0, -1), (1, 0), (0, 0))]:
            nb = pad[1 + di:1 + di + ny, 1 + dj:1 + dj + nx]
            ei, ej = np.nonzero(mask & ~nb)
            if len(ei) == 0: continue
            At = vid[ei + A[0], ej + A[1]]; Bt = vid[ei + B[0], ej + B[1]]
            Ab = np.column_stack([V[At, 0], V[At, 1], np.full(len(At), base_z)]); Bb = np.column_stack([V[Bt, 0], V[Bt, 1], np.full(len(Bt), base_z)])
            iAb = nv + np.arange(len(At)); iBb = iAb + len(At); nv += 2 * len(At)
            extra_V += [Ab, Bb]; extra_F += [np.stack([iAb, iBb, Bt], 1), np.stack([iAb, Bt, At], 1)]
        if extra_V:
            V = np.vstack([V] + extra_V); F += extra_F; is_top = np.concatenate([is_top, np.zeros(len(V) - len(is_top), bool)])
    F = np.vstack(F)
    used = np.unique(F); remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
    return V[used], remap[F], is_top[used]

def to_trimesh(V, F, colors=None, name=None):
    m = trimesh.Trimesh(vertices=to_export(V), faces=F, process=False)
    if colors is not None: m.visual.vertex_colors = colors
    if name: m.metadata['name'] = name
    return m

WALL = np.array([214, 206, 194, 255], np.uint8)

def color_vertices(V, is_top, fallback=(200, 120, 100)):
    cols = np.tile(WALL, (len(V), 1))
    if is_top.any():
        s = sample_naip(V[is_top, 0], V[is_top, 1])
        if s is None: s = np.tile(np.array(fallback, np.uint8), (int(is_top.sum()), 1))
        cols[is_top, :3] = s
    return cols

# ----------------------------------------------------------------------------- buildings
scene_b = trimesh.Scene()
building_mask_all = np.zeros((G.ny, G.nx), bool)
enriched = []; stats = dict(buildings=0, measured=0, lod2=0, lod1=0, skipped=0)
cx_all, cy_all = G.centers()

for k, f in enumerate(feats):
    p = props_of(f); g = f['geometry']
    if not p['building'] or g['type'] not in ('Polygon', 'MultiPolygon'):
        enriched.append(f); continue
    try:
        geom = shape(g)
    except Exception:
        enriched.append(f); continue
    if geom.is_empty: continue
    # to local coords
    def _tf(geom):
        return shapely.transform(geom, lambda a: np.column_stack(frame.from_lonlat(a[:, 0], a[:, 1])))
    loc = _tf(geom)
    if not loc.is_valid: loc = loc.buffer(0)
    if loc.is_empty or loc.area < 3: stats['skipped'] += 1; continue
    bx0, by0, bx1, by1 = loc.bounds
    j0 = max(0, int((bx0 - G.x0) / G.res) - 1); j1 = min(G.nx, int((bx1 - G.x0) / G.res) + 2)
    i0 = max(0, int((by0 - G.y0) / G.res) - 1); i1 = min(G.ny, int((by1 - G.y0) / G.res) + 2)
    if j1 <= j0 or i1 <= i0: stats['skipped'] += 1; continue
    cx, cy = G.centers(i0, i1, j0, j1)
    mask = shapely.contains_xy(loc, cx, cy)
    name = p['name'] or f"{p['building']}_{p['id'] or k}"
    base = float(np.nanmedian(DTM_fine[i0:i1, j0:j1][mask])) if (mask.any() and cloud is not None) else 0.0
    height = None; source = 'estimate'; eave = ridge = None; top = None
    if cloud is not None and mask.any():
        roofgrid = DSM[i0:i1, j0:j1].copy()
        if DSM6 is not None:
            r6 = DSM6[i0:i1, j0:j1]
            if np.isfinite(r6[mask]).mean() >= 0.3: roofgrid = np.where(np.isfinite(r6), r6, np.nan)
        vals = roofgrid[mask] - base; vals = vals[np.isfinite(vals)]
        if len(vals) >= 3:
            ridge = float(np.percentile(vals, 97)); eave = float(np.percentile(vals, 20)); height = max(2.5, ridge); source = 'lidar'; stats['measured'] += 1
            top = np.where(mask, roofgrid, np.nan); top = fill_nearest(top); top = ndimage.median_filter(top, 3)
            top = np.clip(top, base + max(2.0, eave - 1.0), base + ridge + 1.5)
    if height is None:
        height = p['height'] if p['height'] else (p['levels'] * 3.5 + 1.0 if p['levels'] else {'house': 7.5, 'residential': 7.5, 'garage': 3.5, 'shed': 3.0, 'church': 13.0, 'university': 14.0, 'school': 11.0, 'dormitory': 16.0, 'stadium': 18.0}.get(str(p['building']), 9.0))
        source = 'tag' if (p['height'] or p['levels']) else 'estimate'
        top = np.full(mask.shape, base + height)
    building_mask_all[i0:i1, j0:j1] |= mask
    # mesh
    mesh = None
    if mask.sum() >= 2:
        V, F, is_top = heightfield_mesh(mask, top, base - 0.6, G.x0 + j0 * G.res, G.y0 + i0 * G.res, G.res, walls=True)
        mesh = to_trimesh(V, F, color_vertices(V, is_top), name); stats['lod2' if source == 'lidar' else 'lod1'] += 1
    else:  # tiny footprint: exact extrusion of the polygon
        try:
            polys = [loc] if isinstance(loc, Polygon) else list(loc.geoms)
            parts = [trimesh.creation.extrude_polygon(pg, height) for pg in polys if pg.area > 0.5]
            if parts:
                mesh = trimesh.util.concatenate(parts); mesh.apply_translation([0, 0, base - 0.6])
                mesh = trimesh.Trimesh(vertices=to_export(mesh.vertices), faces=mesh.faces, process=False)
                mesh.visual.vertex_colors = np.tile(WALL, (len(mesh.vertices), 1)); stats['lod1'] += 1
        except Exception as e:
            log(f'extrude failed for {name}: {e}')
    if mesh is None: stats['skipped'] += 1; continue
    stats['buildings'] += 1
    scene_b.add_geometry(mesh, geom_name=f'{name}#{k}', node_name=f'{name}#{k}')
    props = dict(f.get('properties') or {})
    tags = props['tags'] if isinstance(props.get('tags'), dict) else props
    tags.update({'height': round(float(height), 1), 'height:source': source, 'name': name if p['name'] else tags.get('name')})
    if p['name'] is None: tags.pop('name', None)
    if eave is not None: tags['roof:height'] = round(max(0.0, ridge - eave), 1); tags['est:eave'] = round(eave, 1)
    tags['est:base'] = round(base, 2)
    f2 = dict(f); f2['properties'] = props; enriched.append(f2)
    if stats['buildings'] % 250 == 0: log(f"  {stats['buildings']} buildings so far …")
log(f"buildings: {stats}")

# ----------------------------------------------------------------------------- trees
trees = []
if cloud is not None:
    CHM = DSM - DTM_fine
    if VEG is not None:
        veg = (VEG > 0) & (VEG >= BLD) & ~building_mask_all
    else:
        veg = (CHM > 2.5) & ~ndimage.binary_dilation(building_mask_all, iterations=2)
    chm = np.where(veg & np.isfinite(CHM), CHM, 0.0)
    sm = ndimage.gaussian_filter(chm, 1.0 / G.res)
    win = max(3, int(round(7.0 / G.res)) | 1)
    peaks = (sm == ndimage.maximum_filter(sm, size=win)) & (sm > 3.0) & veg
    pi, pj = np.nonzero(peaks)
    h = chm[pi, pj]; order = np.argsort(-h)[:args.max_trees]
    for i, j in zip(pi[order], pj[order]):
        hh = float(chm[i, j]); trees.append(dict(x=float(G.x0 + (j + 0.5) * G.res), y=float(G.y0 + (i + 0.5) * G.res), z=float(DTM_fine[i, j]), height=round(hh, 1), radius=round(float(np.clip(0.35 * hh, 1.5, 7.0)), 1)))
    log(f'trees detected from canopy: {len(trees)}')

# ----------------------------------------------------------------------------- exports
def export(scene_or_mesh, name):
    path = os.path.join(args.out, name + '.glb'); scene_or_mesh.export(path)
    if args.obj:
        try: scene_or_mesh.export(os.path.join(args.out, name + '.obj'))
        except Exception as e: log(f'obj export of {name} failed: {e}')
    log(f'wrote {path} ({os.path.getsize(path) / 1048576:.1f} MB)')

if stats['buildings']:
    export(scene_b, 'tulane_buildings')

# terrain
mask_t = np.ones(DTM.shape, bool)
V, F, _ = heightfield_mesh(mask_t, DTM, 0.0, GT.x0, GT.y0, GT.res, walls=False)
terrain = trimesh.Trimesh(vertices=to_export(V), faces=F, process=False)
if naip is not None:
    terrain.visual = trimesh.visual.TextureVisuals(uv=uv_naip(V[:, 0], V[:, 1]), image=naip['img'])
else:
    terrain.visual.vertex_colors = np.tile(np.array([158, 205, 96, 255], np.uint8), (len(V), 1))
terrain.metadata['name'] = 'terrain'
export(terrain, 'tulane_terrain')

# trees: instanced crowns + trunks
if trees:
    scene_t = trimesh.Scene()
    crowns = {}
    for tint, col in (('light', [120, 178, 78, 255]), ('mid', [86, 152, 62, 255]), ('dark', [64, 122, 48, 255])):
        m = trimesh.creation.icosphere(subdivisions=1, radius=1.0); m.visual.face_colors = np.tile(np.array(col, np.uint8), (len(m.faces), 1)); crowns[tint] = m
    trunk = trimesh.creation.cylinder(radius=1.0, height=1.0, sections=8); trunk.visual.face_colors = np.tile(np.array([111, 75, 51, 255], np.uint8), (len(trunk.faces), 1))
    for tint, m in crowns.items(): scene_t.geometry[f'crown_{tint}'] = m      # one shared mesh per tint, instanced by nodes
    scene_t.geometry['trunk'] = trunk
    Rx = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])  # cylinder axis z -> y
    for i, t in enumerate(trees):
        tint = 'light' if t['height'] < 8 else ('mid' if t['height'] < 14 else 'dark')
        r = t['radius']; ch = max(2.0, t['height'] * 0.6); cz = t['z'] + t['height'] - ch / 2
        Tc = np.diag([r, ch / 2, r, 1.0]); Tc[:3, 3] = [t['x'], cz, -t['y']]
        scene_t.graph.update(frame_to=f'tree_{i}', frame_from='world', matrix=Tc, geometry=f'crown_{tint}')
        th = max(0.5, t['height'] - ch); Tt = np.eye(4); Tt[:3, :3] = np.diag([r * 0.12, th, r * 0.12]); Tt[:3, 3] = [t['x'], t['z'] + th / 2, -t['y']]
        scene_t.graph.update(frame_to=f'trunk_{i}', frame_from='world', matrix=Tt @ Rx, geometry='trunk')
    export(scene_t, 'tulane_trees')
    with open(os.path.join(args.out, 'tulane_trees.json'), 'w') as fh:
        json.dump(dict(frame='meters; x east (or along St. Charles with --align), y north, z = ground elevation; glTF uses (x, up, -y)', trees=trees), fh)

# whole scanned surface
if args.surface and cloud is not None:
    GS = Grid(args.surface_res); good = ~np.isin(c, [7, 18]); S = fill_nearest(GS.max(x[good], y[good], z[good]))
    V, F, _ = heightfield_mesh(np.ones(S.shape, bool), S, 0.0, GS.x0, GS.y0, GS.res, walls=False)
    surf = trimesh.Trimesh(vertices=to_export(V), faces=F, process=False)
    if naip is not None: surf.visual = trimesh.visual.TextureVisuals(uv=uv_naip(V[:, 0], V[:, 1]), image=naip['img'])
    else: surf.visual.vertex_colors = np.tile(np.array([190, 190, 180, 255], np.uint8), (len(V), 1))
    export(surf, 'tulane_scan_surface')

# enriched geojson (loads into the voxel viewer; heights now measured)
with open(os.path.join(args.out, 'tulane_enriched.geojson'), 'w', encoding='utf-8') as fh:
    json.dump(dict(type='FeatureCollection', features=enriched), fh)
log('wrote tulane_enriched.geojson')

# preview
try:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib.colors import LightSource
    fig, ax = plt.subplots(figsize=(10, 10 * (Y1 - Y0) / (X1 - X0)))
    if DSM is not None:
        ls = LightSource(azdeg=315, altdeg=45); ax.imshow(ls.shade(fill_nearest(DSM), cmap=plt.cm.gray, vert_exag=1.5, blend_mode='soft'), extent=[X0, X1, Y0, Y1], origin='lower')
    for f in enriched:
        g = f['geometry']; pp = props_of(f)
        if pp['building'] and g['type'] in ('Polygon', 'MultiPolygon'):
            for poly in ([g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']):
                ring = np.array(poly[0]); lx, ly = frame.from_lonlat(ring[:, 0], ring[:, 1]); ax.plot(lx, ly, color='#ff6a3d', lw=0.5)
    ax.set_aspect('equal'); ax.set_title('LiDAR surface (hillshade) with footprints'); fig.savefig(os.path.join(args.out, 'preview_dsm.png'), dpi=130, bbox_inches='tight')
    log('wrote preview_dsm.png')
except Exception as e:
    log(f'preview skipped: {e}')

stats.update(trees=len(trees), lidar=cloud is not None, orthophoto=naip is not None, frame='aligned to St. Charles' if args.align_st_charles else 'north-up')
json.dump(stats, open(os.path.join(args.out, 'model_stats.json'), 'w'), indent=1)
log('done', stats)
