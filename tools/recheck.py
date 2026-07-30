"""RECHECK — were the first run's candidates killed by a broken control?

The first overnight run produced candidates at held-out r = +0.42 to +0.44.
The forensic pass ran each on "blank papyrus" and reported |r| = 0.21 to 0.47,
concluding they detect papyrus condition rather than ink. That conclusion is
now in doubt, because the control selected segments by WHOLE-MAP ink coverage
and then scored them through a function that requires 5-85% ink coverage in the
CROP. Its controls therefore only ever ran on crops full of ink — it was
measuring ink detection and calling it failure.

This re-runs exactly those variants against:

  blank      controls whose ALIGNED CROP is verified <= 0.5% ink
  blind      PHerc0172, 1.9 voxels through the ink layer — text present,
             ink never sampled. Correlation there cannot be ink.
  held-out   the four resolvable held-out scrolls

If a candidate holds up on held-out ink while going quiet on both controls, the
first run killed something real and it needs the full battery. If it fires on
verified-blank crops, the original verdict was right for the wrong reason.

Usage: python3 recheck.py
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P
import depth_pca as DP

_argv, sys.argv = sys.argv, [sys.argv[0]]
import nightshift as NS
import rti as RTI
sys.argv = _argv

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "findings")

# the exact variants the first run surfaced, from its alert and verdict logs
CANDIDATES = [
    {"name": "offaxis+hfenergy+chandark", "features": ["offaxis", "hfenergy", "chandark"],
     "weights": [0.7, -1.0, 0.5], "scale_um": 1000.0, "hp_um": 160.0, "proud_um": 900.0,
     "chan_um": 200.0, "chan_pct": 60, "plate_lo_um": 100.0, "plate_hi_um": 300.0,
     "depth_band": 8},
    {"name": "offaxis+hfenergy", "features": ["offaxis", "hfenergy"],
     "weights": [0.7, -1.0], "scale_um": 1000.0, "hp_um": 160.0, "proud_um": 900.0,
     "chan_um": 200.0, "chan_pct": 60, "plate_lo_um": 100.0, "plate_hi_um": 300.0,
     "depth_band": 8},
    {"name": "offaxis", "features": ["offaxis"], "weights": [1.0],
     "scale_um": 750.0, "hp_um": 160.0, "proud_um": 500.0, "chan_um": 200.0,
     "chan_pct": 70, "plate_lo_um": 100.0, "plate_hi_um": 500.0, "depth_band": 8},
    {"name": "disorder+offaxis+sharp", "features": ["disorder", "offaxis", "sharp"],
     "weights": [1.0, 0.7, 0.5], "scale_um": 750.0, "hp_um": 160.0, "proud_um": 500.0,
     "chan_um": 200.0, "chan_pct": 70, "plate_lo_um": 100.0, "plate_hi_um": 500.0,
     "depth_band": 8},
]


def fmap(tile, V):
    img = P.mid_image(tile, int(V["depth_band"]))
    if (img > 0).mean() < 0.5:
        return None
    F = NS.make_features(img, tile["um"], V)
    out = None
    for nm, w in zip(V["features"], V["weights"]):
        t = w*P.z(F[nm])
        out = t if out is None else out + t
    return out


def med(tiles, V, fn, gate):
    rs = []
    for t in tiles:
        tile = P.load_tile(t)
        if tile is None:
            continue
        try:
            f = fmap(tile, V)
        except Exception:
            continue
        if f is None:
            continue
        s = fn(f, tile, require_cov=gate)
        if s:
            rs.append(abs(s["r"]))
    return (float(np.median(rs)) if rs else None), len(rs)


def main():
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blind_pool = [t for s in bs for t in by[s]]
    rng = np.random.default_rng(11)

    print("building a VERIFIED-blank control set (crop <= 0.5% ink) …", flush=True)
    negs = P.warm(P.find_negatives(held, n=8), verbose=False)
    for t in negs:
        print(f"    control {t['scroll']:12s} crop cov = {P.crop_coverage(t):.4f}")
    pick = P.warm([held[i] for i in rng.permutation(len(held))[:14]], verbose=False)
    blind = P.warm([blind_pool[i] for i in
                    np.random.default_rng(0).permutation(len(blind_pool))[:6]],
                   verbose=False)
    print(f"\n{len(pick)} held-out, {len(negs)} verified-blank, {len(blind)} blind tiles\n")

    print(f"{'candidate':28s} {'held-out':>9s} {'blank':>8s} {'blind':>8s}  verdict")
    print("-"*72)
    rows = []
    for V in CANDIDATES:
        h, nh = med(pick, V, P.score_vs_ink, (0.02, 0.90))
        # A verified-blank crop thresholds to all zeros, so the binarised
        # scorer returns None and an unmeasured control would read as a pass.
        # neg_control correlates against the RAW ink-detection map, which still
        # varies in blank regions, so the control is always measurable.
        b = P.neg_control(lambda tl, _V=V: fmap(tl, _V), negs)
        nb = len(negs)
        d, nd = med(blind, V, P.score_vs_ink, (0.02, 0.90))
        if h is None:
            print(f"{V['name']:28s} too few tiles")
            continue
        # an UNMEASURED control is never a pass
        alive = (h >= 0.25 and b is not None and b <= 0.12
                 and (d is None or d <= 0.15))
        rows.append(dict(name=V["name"], heldout=h, blank=b, blind=d,
                         n_held=nh, n_blank=nb, n_blind=nd, alive=bool(alive)))
        f = lambda x: "  --  " if x is None else f"{x:6.3f}"
        print(f"{V['name']:28s} {f(h):>9s} {f(b):>8s} {f(d):>8s}  "
              f"{'ALIVE — first run killed it wrongly' if alive else 'dead'}")

    json.dump(rows, open(os.path.join(OUT, "recheck.json"), "w"), indent=1)
    print("\n" + "="*72)
    alive = [r for r in rows if r["alive"]]
    if alive:
        print("The first run's negative control was broken AND these survive a\n"
              "correct one. They need the full forensic battery before anyone\n"
              "says anything out loud.")
    else:
        print("The control was broken, but these candidates die against a correct\n"
              "one too. The original verdict stands — for a different reason than\n"
              "the one recorded. Both facts belong in the writeup.")
    return rows


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"{time.time()-t0:.0f}s")
