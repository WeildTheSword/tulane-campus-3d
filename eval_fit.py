#!/usr/bin/env python3
"""eval_fit.py — compare two builds' tulane_enriched.geojson: landmark heights/roofs and the roof-fit metrics.

  python eval_fit.py out/core out/core_v2            # before → after
  python eval_fit.py out/core_v2                     # just report one build
"""
import json, sys, os
import numpy as np

LANDMARKS = ['Gibson Hall', 'Tilton Memorial Hall', 'Dinwiddie Hall', 'Newcomb Hall', 'Howard Tilton Memorial Library', 'McAlister Auditorium',
             'Yulman Stadium', 'Reily Student Recreation Center', 'Lavin-Bernick University Center (LBC)', 'Richardson Memorial Hall', 'Percival Stern Hall']

def load(d):
    gj = json.load(open(os.path.join(d, 'tulane_enriched.geojson'), encoding='utf-8'))
    out = {}
    for f in gj['features']:
        p = f.get('properties') or {}; t = p.get('tags') if isinstance(p.get('tags'), dict) else p
        if 'height:source' in t: out[t.get('name') or f"{t.get('building')}_{p.get('id')}"] = t
    return out

dirs = sys.argv[1:] or ['out/core_v2']
A = load(dirs[0]); B = load(dirs[1]) if len(dirs) > 1 else None
def g(t, k, nd='—'):
    v = t.get(k); return nd if v is None else v
print(f"{'building':30s} {'height':>12s} {'roof':>10s} {'planes':>6s} {'cover':>5s} {'rmse':>10s} {'inlier':>6s}")
for n in LANDMARKS:
    a = A.get(n); b = B.get(n) if B else None
    if not a and not b: continue
    t = b or a; o = a if B else {}
    arrow = lambda k, f='{}': (f.format(g(o, k)) + '→' if B and o else '') + f.format(g(t, k))
    print(f"{n[:30]:30s} {arrow('height'):>12s} {arrow('roof:height'):>10s} {str(g(t, 'roof:planes')):>6s} {str(g(t, 'fit:plane_cover')):>5s} {arrow('fit:rmse'):>10s} {str(g(t, 'fit:inlier')):>6s}")
for d, S in ((dirs[0], A), (dirs[1], B)) if B else ((dirs[0], A),):
    r = np.array([t['fit:rmse'] for t in S.values() if 'fit:rmse' in t]); raw = np.array([t['fit:rmse_raw'] for t in S.values() if 'fit:rmse_raw' in t])
    inl = np.array([t['fit:inlier'] for t in S.values() if 'fit:inlier' in t]); pl = np.array([t.get('roof:planes', 0) for t in S.values() if 'fit:rmse' in t])
    orph = sum(1 for t in S.values() if t.get('source') == 'lidar-unmapped')
    if len(r):
        print(f"\n{d}: {len(r)} measured · rmse median {np.median(r):.2f} mean {r.mean():.2f} (previous method mean {raw.mean():.2f}) · inlier mean {inl.mean():.3f} · planar roofs {int((pl > 0).sum())} ({(pl > 0).mean() * 100:.0f}%) · unmapped structures {orph}")
        print('  rmse buckets  ≤0.1: {:.0%}  ≤0.25: {:.0%}  ≤0.5: {:.0%}  >1.0: {:.0%}'.format(*(np.mean(r <= k) for k in (0.1, 0.25, 0.5)), np.mean(r > 1.0)))
    else:
        print(f"\n{d}: no fit metrics (older build)")
