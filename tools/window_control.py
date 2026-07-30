"""WINDOW CONTROL — the aimed-window finding vs the blind scroll.

Two independent window draws showed within-window excess of +0.10..+0.22
(50-79% significant) for the texture/weave family across 14-16 segments.
The one missing control: PHerc0172, whose 7.91 um scan never sampled the
ink layer (1.9 voxels). Same aiming, same features, same params, same
nulls. Excess THERE cannot be ink — if the blind scroll shows the same
excess, the finding is an artifact of aiming at label structure; if it
stays near zero, the finding survives its strongest control.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P
import native as N

_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import dogs as D
finally:
    sys.argv = _argv

FEATURES = ["weave_fill", "weave_amp", "hfenergy", "offaxis", "sharp"]

tg = [t for t in P.targets() if t["scroll"] == "PHerc0172"][:14]
rows = {f: [] for f in FEATURES}
scored = 0
for i, t0 in enumerate(tg):
    t = dict(t0, seg=t0["seg"] + "@ctl")
    ink, iy, ix = N.aim(t0)
    if ink is None:
        continue
    tile = N.aimed_fetch(t, 2, ink, iy, ix)
    if tile is None:
        continue
    scored += 1
    print(f"  [{i}] window ({iy},{ix}) um={tile['um']:.2f}", flush=True)
    for f in FEATURES:
        for d in range(2):
            rng = np.random.default_rng(1000 + d)
            V = D.sample_variant(rng)
            V["features"], V["weights"] = [f], [1.0]
            try:
                fm = D.feature_map(tile, V)
            except Exception:
                fm = None
            if fm is None:
                continue
            r = P.auc_vs_ink(fm, tile)
            if r is not None and r["null_median"] is not None:
                rows[f].append(dict(excess=r["auc"] - r["null_median"], p=r["p"]))
    P._mem.clear()

print(f"\nblind-scroll aimed windows scored: {scored}")
print(f"{'feature':12s} {'n':>3s} {'excess':>8s} {'sig':>6s}   (ink-scroll reference)")
ref = {"weave_fill": "+0.20/+0.22", "weave_amp": "+0.20/+0.22",
       "hfenergy": "+0.18/+0.21", "offaxis": "+0.12/+0.20", "sharp": "+0.16"}
out = {}
for f in FEATURES:
    v = rows[f]
    if not v:
        print(f"{f:12s}   0")
        continue
    me = float(np.median([x["excess"] for x in v]))
    sig = sum(1 for x in v if x["p"] < 0.05)
    out[f] = dict(n=len(v), excess=me, sig=f"{sig}/{len(v)}")
    print(f"{f:12s} {len(v):3d} {me:+8.3f} {sig:3d}/{len(v)}   ({ref.get(f,'')})")
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "findings", "window_control.json"), "w"),
          indent=1)
print("\nExcess here ~= ink-scroll excess -> ARTIFACT. Near zero -> finding survives.")
