#!/usr/bin/env python3
"""pack_web.py — squeeze a built campus model into a single self-contained HTML page (≤ ~10 MB) for phones and sharing.

Takes the glb/json outputs of build_model.py and writes compact GLBs (int16 quantized positions, uint8 colours, uint16 indices,
no normals — the page computes them; building names travel in node extras), a cropped JPEG orthophoto instead of the 57 MB PNG, and the tree list as a flat array,
then fills viewer/scan_template.html.

  python pack_web.py --fine out/core --coarse out/core2 --template viewer/scan_template.html --out out/tulane_scan.html
"""
import argparse, base64, io, json, os, struct, sys
import numpy as np
import trimesh
from PIL import Image
from scipy.spatial import cKDTree
try:
    import fast_simplification
except ImportError:
    fast_simplification = None

ap = argparse.ArgumentParser()
ap.add_argument('--fine', default='out/core', help='build dir with fine (1 m) roofs; named buildings are taken from here')
ap.add_argument('--coarse', default=None, help='build dir with coarse (2 m) roofs; unnamed buildings are taken from here (default: same as --fine)')
ap.add_argument('--template', default='viewer/scan_template.html')
ap.add_argument('--naip', default='data/naip.png')
ap.add_argument('--tex', type=int, default=1800, help='orthophoto crop long edge in px')
ap.add_argument('--jpeg', type=int, default=78)
ap.add_argument('--quant', type=float, default=0.05, help='position quantum in m (int16 positions via KHR_mesh_quantization); 0 = float32')
ap.add_argument('--decimate', type=float, default=0.7, help='quadric-decimate unnamed buildings by this fraction (planar roofs survive it); 0 = off')
ap.add_argument('--decimate-named', type=float, default=0.4, help='same for named buildings')
ap.add_argument('--out', default='out/tulane_scan.html')
args = ap.parse_args(); coarse = args.coarse or args.fine

GENERIC = {'yes', 'house', 'residential', 'apartments', 'garage', 'shed', 'roof', 'detached', 'commercial', 'retail', 'school', 'university',
           'church', 'dormitory', 'office', 'industrial', 'hut', 'terrace', 'parking', 'stadium', 'hospital', 'hotel', 'public', 'service',
           'greenhouse', 'warehouse', 'kiosk', 'semidetached_house', 'bungalow', 'construction', 'sports_centre', 'carport', 'garages'}
def is_named(node):   # build_model names nodes '<name>#<k>'; unnamed footprints get '<building tag>_<osm id>#<k>'
    base = node.rsplit('#', 1)[0]
    stem = base.rsplit('_', 1)[0] if base.rsplit('_', 1)[-1].isdigit() else base
    first = stem.lower().split('_')[0]           # 'yes_city_12' (city footprint) -> 'yes'
    return first not in GENERIC and stem.lower() not in GENERIC and not base.isdigit() and not base.startswith('structure_')   # scan-only structures and city footprints have no name to show

# ----------------------------------------------------------------------------- minimal GLB writer
def pad4(b, fill=b'\x00'):
    return b + fill * ((4 - len(b) % 4) % 4)

class GLB:
    def __init__(self):
        self.bin = bytearray(); self.views = []; self.accs = []; self.meshes = []; self.nodes = []; self.images = []; self.textures = []; self.materials = []; self.samplers = []
    def view(self, data, target=None):
        off = len(self.bin); self.bin += pad4(bytes(data)); v = dict(buffer=0, byteOffset=off, byteLength=len(data))
        if target: v['target'] = target
        self.views.append(v); return len(self.views) - 1
    def acc(self, arr, ctype, atype, target, normalized=False, minmax=False):
        arr = np.ascontiguousarray(arr); a = dict(bufferView=self.view(arr.tobytes(), target), componentType=ctype, count=len(arr), type=atype)
        if normalized: a['normalized'] = True
        if minmax: a['min'] = arr.min(0).tolist(); a['max'] = arr.max(0).tolist()
        self.accs.append(a); return len(self.accs) - 1
    def mesh(self, name, V, F, colors=None, uv=None, material=None, label=None, extras=None):
        if args.quant:   # int16 positions in units of --quant metres; the node scale restores metres (KHR_mesh_quantization)
            Q = np.rint(np.asarray(V, np.float64) / args.quant); assert np.abs(Q).max() < 32767, 'scene too large for int16 at this quantum'
            attrs = {'POSITION': self.acc(Q.astype(np.int16), 5122, 'VEC3', 34962, minmax=True)}
        else: attrs = {'POSITION': self.acc(V.astype(np.float32), 5126, 'VEC3', 34962, minmax=True)}
        if colors is not None: attrs['COLOR_0'] = self.acc(colors.astype(np.uint8), 5121, 'VEC4' if colors.shape[1] == 4 else 'VEC3', 34962, normalized=True)
        if uv is not None: attrs['TEXCOORD_0'] = self.acc(np.rint(np.clip(uv, 0, 1) * 65535).astype(np.uint16), 5123, 'VEC2', 34962, normalized=True) if args.quant else self.acc(uv.astype(np.float32), 5126, 'VEC2', 34962)
        if len(V) < 65535: idx = self.acc(F.astype(np.uint16).ravel(), 5123, 'SCALAR', 34963)
        else: idx = self.acc(F.astype(np.uint32).ravel(), 5125, 'SCALAR', 34963)
        prim = dict(attributes=attrs, indices=idx, mode=4)
        if material is not None: prim['material'] = material
        self.meshes.append(dict(name=name, primitives=[prim])); node = dict(name=name, mesh=len(self.meshes) - 1)
        if args.quant: node['scale'] = [args.quant] * 3
        if label or extras: node['extras'] = dict(extras or {}, **(dict(label=label) if label else {}))   # GLTFLoader sanitizes node names (spaces -> _) but copies extras to userData verbatim
        self.nodes.append(node)
    def texture_material(self, jpeg_bytes):
        self.images.append(dict(bufferView=self.view(jpeg_bytes), mimeType='image/jpeg'))
        self.samplers.append(dict(magFilter=9729, minFilter=9987, wrapS=33071, wrapT=33071))
        self.textures.append(dict(sampler=len(self.samplers) - 1, source=len(self.images) - 1))
        self.materials.append(dict(name='orthophoto', pbrMetallicRoughness=dict(baseColorTexture=dict(index=len(self.textures) - 1), metallicFactor=0.0, roughnessFactor=1.0)))
        return len(self.materials) - 1
    def bytes(self):
        j = dict(asset=dict(version='2.0', generator='tulane-campus-3d pack_web.py'), scene=0, scenes=[dict(nodes=list(range(len(self.nodes))))], nodes=self.nodes, meshes=self.meshes,
                 accessors=self.accs, bufferViews=self.views, buffers=[dict(byteLength=len(self.bin))])
        if self.materials: j.update(materials=self.materials, textures=self.textures, images=self.images, samplers=self.samplers)
        if args.quant: j['extensionsUsed'] = j['extensionsRequired'] = ['KHR_mesh_quantization']
        js = pad4(json.dumps(j, separators=(',', ':')).encode(), b' '); bb = pad4(bytes(self.bin))
        return b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + len(bb)) + struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(bb), 0x004E4942) + bb

def colors_of(g):
    vc = getattr(g.visual, 'vertex_colors', None)
    if vc is None or len(vc) != len(g.vertices): return None
    return np.asarray(vc)[:, :4].astype(np.uint8)

def decimate(V, F, C, frac):
    """Quadric decimation; colours re-attached from the nearest original vertex."""
    if not frac or fast_simplification is None or len(F) < 60: return V, F, C
    V2, F2 = fast_simplification.simplify(np.asarray(V, np.float32), np.asarray(F, np.int64), target_reduction=float(frac), agg=6)
    if len(F2) < 4: return V, F, C
    C2 = C[cKDTree(V).query(V2, k=1)[1]] if C is not None else None
    return V2, F2, C2

def fit_lookup(build_dir):
    """node stem -> fit:rmse from the build's enriched geojson (named: the name; unnamed: '<building>_<osm id>'; scan-only: 'structure_N')."""
    out = {}
    try: gj = json.load(open(os.path.join(build_dir, 'tulane_enriched.geojson'), encoding='utf-8'))
    except FileNotFoundError: return out
    for f in gj['features']:
        p = f.get('properties') or {}; t = p.get('tags') if isinstance(p.get('tags'), dict) else p
        if 'fit:rmse' not in t: continue
        key = t.get('name') or f"{t.get('building')}_{p.get('id')}"
        out[key] = float(t['fit:rmse'])
        if str(p.get('id', '')).startswith('structure_'): out[p['id']] = float(t['fit:rmse'])
    return out

# ----------------------------------------------------------------------------- buildings
def load_scene(p):
    s = trimesh.load(p, force='scene'); return {n: s.geometry[n] for n in s.geometry}
fine = load_scene(os.path.join(args.fine, 'tulane_buildings.glb'))
coarse_s = fine if coarse == args.fine else load_scene(os.path.join(coarse, 'tulane_buildings.glb'))
glb = GLB(); named = 0; fit_f = fit_lookup(args.fine); fit_c = fit_lookup(coarse)
for n, g in fine.items():
    if is_named(n):
        stem = n.rsplit('#', 1)[0]; V, F, C = decimate(g.vertices, g.faces, colors_of(g), args.decimate_named)
        glb.mesh(n, V, F, C, label=stem, extras=dict(fit=fit_f.get(stem))); named += 1
# everything unnamed from the coarse build, merged into a handful of big meshes (fewer draw calls); per-building fit kept as vertex ranges
chunks = []; V = []; F = []; C = []; R = []; off = 0; nhouse = 0
def flush():
    global V, F, C, R, off
    if V: glb.mesh(f'houses_{len(chunks)}', np.vstack(V), np.vstack(F), np.vstack(C), extras=dict(ranges=R)); chunks.append(1)
    V, F, C, R, off = [], [], [], [], 0
for n, g in coarse_s.items():
    if is_named(n): continue
    c = colors_of(g); c = c if c is not None else np.full((len(g.vertices), 4), 210, np.uint8)
    v2, f2, c2 = decimate(g.vertices, g.faces, c, args.decimate)
    stem = n.rsplit('#', 1)[0]; R.append([off, len(v2), fit_c.get(stem)])
    V.append(np.asarray(v2, np.float32)); F.append(np.asarray(f2) + off); C.append(c2); off += len(v2); nhouse += 1
    if off > 60000: flush()
flush()
bld = glb.bytes(); print(f'buildings: {named} named (fine) + {nhouse} unnamed (coarse, {len(chunks)} merged meshes) -> {len(bld) / 1048576:.2f} MB')

# ----------------------------------------------------------------------------- terrain + cropped orthophoto
tg = GLB()
ts = trimesh.load(os.path.join(coarse, 'tulane_terrain.glb'), force='scene'); tm = next(iter(ts.geometry.values()))
uv = np.asarray(tm.visual.uv, np.float64)
u0, v0 = np.clip(uv.min(0), 0, 1); u1, v1 = np.clip(uv.max(0), 0, 1)
Image.MAX_IMAGE_PIXELS = None; img = Image.open(args.naip).convert('RGB'); W, H = img.size
# build_model's uv: u = (lon - minLon)/dLon, v = (lat - minLat)/dLat with v up; PNG row 0 is max lat
box = (int(u0 * W), int((1 - v1) * H), int(np.ceil(u1 * W)), int(np.ceil((1 - v0) * H)))
crop = img.crop(box); scale = args.tex / max(crop.size); crop = crop.resize((max(1, round(crop.size[0] * scale)), max(1, round(crop.size[1] * scale))), Image.LANCZOS)
buf = io.BytesIO(); crop.save(buf, 'JPEG', quality=args.jpeg, optimize=True, progressive=True); jpg = buf.getvalue()
uv2 = np.column_stack([(np.clip(uv[:, 0], u0, u1) - u0) / (u1 - u0), 1 - (np.clip(uv[:, 1], v0, v1) - v0) / (v1 - v0)])   # glTF uv origin is top-left
tg.mesh('terrain', tm.vertices, tm.faces, None, uv2)   # texture ships separately as a data: <img>: GLTFLoader would fetch() a blob: URL for an embedded image, which sandboxed pages (Safari: 'Load failed') block
ter = tg.bytes(); print(f'terrain: {len(tm.vertices)} verts, orthophoto crop {crop.size[0]}x{crop.size[1]} jpeg {len(jpg) / 1048576:.2f} MB -> {len(ter) / 1048576:.2f} MB')

# ----------------------------------------------------------------------------- trees
tj = json.load(open(os.path.join(args.fine, 'tulane_trees.json')))['trees']
trees = [dict(x=round(t['x'], 1), y=round(t['y'], 1), z=round(t['z'], 2), height=round(t['height'], 1), radius=round(t['radius'], 1)) for t in tj]
stats = json.load(open(os.path.join(args.fine, 'model_stats.json')))
try: ortho_meta = json.load(open(os.path.splitext(args.naip)[0] + '.json'))
except FileNotFoundError: ortho_meta = {}
imagery = ortho_meta.get('license', 'aerial orthophoto') + f" · {ortho_meta.get('gsd_m', '?')} m/px"

html = open(args.template, encoding='utf-8').read()
html = html.replace('__BUILDINGS_B64__', base64.b64encode(bld).decode()).replace('__TERRAIN_B64__', base64.b64encode(ter).decode()).replace('__ORTHO_B64__', base64.b64encode(jpg).decode())
html = html.replace('__TREES_JSON__', json.dumps(trees, separators=(',', ':'))).replace('__META_JSON__', json.dumps(dict(stats=stats, named=named, unnamed=nhouse, imagery=imagery)))
os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True); open(args.out, 'w', encoding='utf-8').write(html)
print(f'wrote {args.out} ({len(html.encode()) / 1048576:.2f} MB)')
