#!/usr/bin/env python3
"""facade_extract.py — derive a building's facade spec from its photos with deterministic code only (no LLM, no API).

The idea: photos give ratios and colours; the LiDAR model gives the ruler. We know the building's height and storey count,
so the vertical repeat found in the image converts pixels to metres, and every other measurement follows in metres.

Per photo:
  masks      sky (blue-dominant, smooth, upper), vegetation (excess green), shadow (low L*)
  building   the largest remaining blob overlapping the image centre
  split      Otsu on L* inside the building -> wall (bright mode) vs opening (dark mode)
  colours    median CIELAB -> sRGB of wall / wall-lit / wall-shade / glazing
  rhythm     autocorrelation of the row- and column-mean "openness" signal -> storey and window periods in pixels
  scale      storey period px  <->  (lidar height / storeys) m
  refwhite   the 98th-percentile lightness of non-sky, non-vegetation pixels — a white-patch reference that cancels exposure
Across photos: CONSENSUS, not an average. Each photo's normalised estimate is a vote; the largest cluster of mutually
agreeing votes (dE < 8) wins. Sunset, night and mis-masked photos disagree with everyone and are outvoted automatically,
so no semantic triage (and no model) is needed to throw them out.

  python facade_extract.py --photos data/photos/howard_tilton --name "Howard Tilton Memorial Library" --out data/facades/howard_tilton.auto.json
  python facade_extract.py ... --compare data/facades/howard_tilton.json      # score against a judged spec
"""
import argparse, glob, json, os, re, sys
import numpy as np
from PIL import Image
from scipy import ndimage, signal
from skimage.color import rgb2lab, lab2rgb
from skimage.filters import threshold_otsu

ap = argparse.ArgumentParser()
ap.add_argument('--photos', required=True, help='directory of photos for one building')
ap.add_argument('--name', required=True, help='building name as it appears in out/tulane_enriched.geojson')
ap.add_argument('--enriched', default='out/tulane_enriched.geojson', help='LiDAR build that supplies height and storey count (the ruler)')
ap.add_argument('--out', default=None, help='write the spec here (default: stdout only)')
ap.add_argument('--compare', default=None, help='judged spec to score against')
ap.add_argument('--max-px', type=int, default=1400, help='downscale long edge to this before analysis')
ap.add_argument('--verbose', action='store_true')
a = ap.parse_args()

Image.MAX_IMAGE_PIXELS = None
hexs = lambda rgb: '#%02x%02x%02x' % tuple(int(round(min(255, max(0, v)))) for v in rgb)
unhex = lambda h: np.array([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)], float)

def dE(h1, h2):
    """CIE76 colour difference between two sRGB hex strings (dE < 2.3 is imperceptible, < 5 is close)."""
    l1, l2 = (rgb2lab(unhex(h).reshape(1, 1, 3) / 255.0).reshape(3) for h in (h1, h2))
    return float(np.linalg.norm(l1 - l2))

# ----------------------------------------------------------------------------- the ruler: height and storeys from our own model
def lidar_ruler(name, path):
    try: gj = json.load(open(path, encoding='utf-8'))
    except FileNotFoundError: return None
    key = re.sub(r'[^a-z0-9]', '', name.lower()); best = None
    for f in gj['features']:
        t = f['properties'].get('tags') or {}
        if re.sub(r'[^a-z0-9]', '', (t.get('name') or '').lower()) == key and t.get('height'):
            if best is None or t['height'] > best['height']: best = t
    if not best: return None
    lv = best.get('building:levels')
    try: lv = int(float(lv))
    except (TypeError, ValueError): lv = None
    h = float(best['height'])
    return dict(height_m=h, height_max_m=best.get('height:max'), levels=lv, storey_h_m=(h / lv if lv else None), roof=best.get('roof:shape'))

# ----------------------------------------------------------------------------- per-photo analysis
def masks(rgb):
    """(sky, vegetation, shadow) boolean masks. All heuristics on plain sRGB — no learned model."""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]; s = rgb.sum(2) + 1e-6
    lab = rgb2lab(rgb / 255.0); L = lab[..., 0]
    smooth = ndimage.uniform_filter(ndimage.generic_gradient_magnitude(L, ndimage.sobel), 9)
    rows = np.linspace(0, 1, rgb.shape[0])[:, None] * np.ones((1, rgb.shape[1]))
    sky = (B / s > 0.37) & (B > R + 8) & (L > 55) & (smooth < 6) & (rows < 0.75)
    sky = ndimage.binary_closing(sky, np.ones((5, 5)))
    veg = ((2.0 * G - R - B) / s > 0.06) & (G > B)                                    # excess-green index
    veg = ndimage.binary_opening(veg, np.ones((3, 3)))
    shadow = (L < max(18.0, np.percentile(L, 12))) & ~sky
    return sky, veg, shadow

def building_mask(rgb, sky, veg):
    """Largest non-sky, non-vegetation blob that touches the middle band of the frame."""
    cand = ndimage.binary_closing(~(sky | veg), np.ones((7, 7)))
    cand = ndimage.binary_fill_holes(cand)
    lab, n = ndimage.label(cand)
    if not n: return None
    H, W = rgb.shape[:2]; centre = np.zeros((H, W), bool); centre[int(H * .25):int(H * .85), int(W * .15):int(W * .85)] = True
    sizes = ndimage.sum(centre, lab, np.arange(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    m = lab == k
    if m.mean() < 0.04: return None
    return m

def openness_periods(open_sig_rows, open_sig_cols):
    """Dominant repeat (in pixels) of the window signal along each axis, by autocorrelation. Returns (period, confidence)."""
    def peak(sig):
        x = sig - sig.mean()
        if x.std() < 1e-6 or len(x) < 40: return None, 0.0
        ac = signal.correlate(x, x, mode='full')[len(x) - 1:]; ac /= ac[0] + 1e-9
        lo = max(4, int(len(x) * 0.01)); hi = int(len(x) * 0.5)
        seg = ac[lo:hi]
        if len(seg) < 5: return None, 0.0
        pk, props = signal.find_peaks(seg, height=0.05, distance=max(3, lo // 2))
        if not len(pk): return None, 0.0
        i = int(pk[np.argmax(props['peak_heights'])])
        return float(i + lo), float(min(1.0, props['peak_heights'].max()))
    return peak(open_sig_rows), peak(open_sig_cols)

def analyse(path, ruler):
    img = Image.open(path).convert('RGB')
    if max(img.size) > a.max_px: img.thumbnail((a.max_px, a.max_px), Image.LANCZOS)
    rgb = np.asarray(img, np.float32)
    sky, veg, shadow = masks(rgb)
    bm = building_mask(rgb, sky, veg)
    if bm is None: return dict(file=os.path.basename(path), skipped='no building mass found')
    lab = rgb2lab(rgb / 255.0); L = lab[..., 0]
    ground = ~(sky | veg)
    refw = float(np.percentile(L[ground], 98)) if ground.sum() > 5000 else 100.0    # white patch: brightest ordinary surface in frame
    inside = bm & ~shadow
    if inside.sum() < 2000: inside = bm
    try: t = threshold_otsu(L[inside])
    except ValueError: return dict(file=os.path.basename(path), skipped='degenerate luminance')
    wall = bm & (L >= t) & ~veg & ~sky                                              # bright mode = opaque wall
    glass = bm & (L < t) & ~veg & ~sky                                              # dark mode = glazing / recesses
    if wall.sum() < 1500: return dict(file=os.path.basename(path), skipped='too little wall')
    def med(m):
        if m.sum() < 200: return None
        return hexs(np.clip(lab2rgb(np.median(lab[m], 0).reshape(1, 1, 3)).reshape(3) * 255, 0, 255))
    wl = L[wall]; lit = wall & (L >= np.percentile(wl, 70)); shd = wall & (L <= np.percentile(wl, 30))
    glass_core = glass   # the whole dark mode: its darkest tail is shadowed recess, not glazing, and code cannot tell the two apart
    even = float(np.percentile(wl, 70) - np.percentile(wl, 30))          # small spread = flat/overcast light -> the best diffuse estimate
    # rhythm: how "open" each row / column of the building is
    ys, xs = np.nonzero(bm); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    cw = (x1 - x0) // 3; xa, xb = x0 + cw, x1 - cw                                  # central third: perspective foreshortening is mildest here
    if xb - xa < 60: xa, xb = x0, x1
    sub_open = glass[y0:y1 + 1, xa:xb + 1].astype(np.float32); sub_b = bm[y0:y1 + 1, xa:xb + 1].astype(np.float32)
    with np.errstate(invalid='ignore', divide='ignore'):
        rows_sig = np.nan_to_num(sub_open.sum(1) / np.maximum(sub_b.sum(1), 1))
        cols_sig = np.nan_to_num(sub_open.sum(0) / np.maximum(sub_b.sum(0), 1))
    (py, cy), (px, cx) = openness_periods(rows_sig, cols_sig)
    return dict(file=os.path.basename(path), wall_px=int(wall.sum()), frac=float(bm.mean()),
                wall=med(wall), wall_lit=med(lit), wall_shade=med(shd), glass=med(glass_core), even=round(even, 1), refw=round(refw, 1),
                storey_px=py, storey_conf=round(cy, 3), window_px=px, window_conf=round(cx, 3),
                bbox_px=[int(x0), int(y0), int(x1), int(y1)], height_px=int(y1 - y0 + 1))

# ----------------------------------------------------------------------------- run
photos = [p for p in sorted(glob.glob(os.path.join(a.photos, '*'))) if p.lower().endswith(('.jpg', '.jpeg', '.png'))]
ruler = lidar_ruler(a.name, a.enriched)
print(f'{a.name}: {len(photos)} photos; ruler = {ruler}')
rows = []
for p in photos:
    r = analyse(p, ruler)
    rows.append(r)
    if a.verbose or r.get('skipped'):
        print(f"  {r['file'][:58]:58s} {r.get('skipped') or f'wall {r[chr(39)+chr(39)] if False else r['wall']} glass {r['glass']} storey {r['storey_px']}px({r['storey_conf']}) win {r['window_px']}px({r['window_conf']})'}")
ok = [r for r in rows if not r.get('skipped')]
if not ok: sys.exit('no photo yielded a building mass')

REF_L = 88.0        # canonical lightness of a lit pale surface; every photo is rescaled so its white patch sits here
Y_of = lambda L: ((L + 16.0) / 116.0) ** 3 if L > 8.0 else L / 903.3            # CIE L* <-> linear luminance
L_of = lambda Y: float(np.clip(116.0 * (Y ** (1.0 / 3.0)) - 16.0 if Y > 0.008856 else 903.3 * Y, 0, 100))

def wmed(key, radius=8.0, normalise=True):
    # normalise=False for glazing: exposure normalisation estimates diffuse albedo, which is meaningful for opaque matte
    # surfaces and meaningless for specular glass, whose apparent colour is reflected sky rather than its own reflectance.
    """Consensus across photos: normalise each estimate by that photo's white patch, then return the centroid of the
    largest mutually-agreeing cluster (CIE76 dE < radius). Robust to sunset/night/mis-masked photos without triage."""
    est = []
    for r in ok:
        if not r.get(key): continue
        v = rgb2lab(unhex(r[key]).reshape(1, 1, 3) / 255.0).reshape(3).copy()
        if normalise: v[0] = L_of(Y_of(v[0]) * (Y_of(REF_L) / max(Y_of(r.get('refw', 100.0)), 1e-6)))   # exposure is linear in luminance, not in L*
        est.append(v)
    if not est: return None, 0, 0
    labs = np.array(est); best = (0, labs[0])
    for c in labs:
        m = np.linalg.norm(labs - c, axis=1) < radius
        if m.sum() > best[0]: best = (int(m.sum()), labs[m].mean(0))
    return hexs(np.clip(lab2rgb(best[1].reshape(1, 1, 3)).reshape(3) * 255, 0, 255)), best[0], len(labs)

# metric scale: the storey repeat in pixels equals (height / levels) metres
scale = []
if ruler and ruler.get('storey_h_m'):
    for r in ok:
        if r['storey_px'] and r['storey_conf'] > 0.15: scale.append((ruler['storey_h_m'] / r['storey_px'], r['storey_conf'], r))
m_per_px = float(np.median([s for s, _, _ in scale])) if scale else None
win_m = None
if m_per_px:
    w = [r['window_px'] * m_per_px for _, _, r in scale if r['window_px'] and r['window_conf'] > 0.15]
    if w: win_m = float(np.median(w))

spec = dict(building=dict(name=a.name), method='deterministic (facade_extract.py): masks + Otsu split + CIELAB medians + autocorrelation rhythm; scale from the LiDAR storey height',
            photos_used=len(ok), photos_skipped=len(rows) - len(ok), lidar=ruler,
            render=dict(wall=wmed('wall')[0], glass=wmed('glass', normalise=False)[0]),
            consensus={k: dict(zip(('value', 'agreeing', 'photos'), wmed(k, normalise=(k != 'glass')))) for k in ('wall', 'wall_lit', 'wall_shade', 'glass')},
            confidence=dict(wall=0.8, wall_lit=0.7, wall_shade=0.6, window_pitch=0.75, storey_h=0.9,
                            glass=0.3, _glass_note='LOW: the dark mode mixes glazing with shadowed recesses and no threshold separates them '
                            'without knowing what a window is — validated against the judged Howard-Tilton spec at dE 11-12 either way. '
                            'This is the one field where a vision pass still earns its cost.'),
            measured=dict(wall=wmed('wall')[0], wall_lit=wmed('wall_lit')[0], wall_shade=wmed('wall_shade')[0], glass=wmed('glass', normalise=False)[0],
                          m_per_px=m_per_px, window_pitch_m=round(win_m, 2) if win_m else None,
                          storey_h_m=round(ruler['storey_h_m'], 2) if ruler and ruler.get('storey_h_m') else None),
            per_photo=ok)
print(json.dumps({k: v for k, v in spec.items() if k != 'per_photo'}, indent=1)[:1400])
if a.out:
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True); json.dump(spec, open(a.out, 'w'), indent=1); print('wrote', a.out)

if a.compare:
    j = json.load(open(a.compare, encoding='utf-8')); r = j.get('render') or {}
    print(f"\n--- scored against {a.compare} (judged two-pass spec) ---")
    print(f"{'field':14s} {'judged':>9s} {'auto':>9s} {'dE':>6s}   verdict")
    for k, jk in (('wall', 'wall'), ('glass', 'glass')):
        jv, av = r.get(jk), spec['measured'].get(k)
        if jv and av:
            d = dE(jv, av); print(f'{k:14s} {jv:>9s} {av:>9s} {d:6.1f}   {"match (dE<5)" if d < 5 else "close (dE<10)" if d < 10 else "MISS"}')
    jp = r.get('pitch'); ap_ = spec['measured'].get('window_pitch_m')
    if jp and ap_: print(f"{'window pitch':14s} {jp:>8.2f}m {ap_:>8.2f}m {'':6s}   {'match' if abs(jp-ap_)/jp < 0.2 else 'MISS'} ({abs(jp-ap_)/jp*100:.0f}% off)")
    js = r.get('storeys'); a_s = spec['measured'].get('storey_h_m')
    if js and a_s: print(f"{'storey h':14s} {np.mean(js):>8.2f}m {a_s:>8.2f}m {'':6s}   (judged mean vs height/levels)")
