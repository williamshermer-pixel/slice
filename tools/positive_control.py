"""POSITIVE CONTROL — is the pipeline capable of finding ink at all?

THE PROBLEM THIS EXISTS TO FIX

Fourteen mechanisms have now been declared dead. Every tool in this project is
designed to KILL a candidate: spatial nulls, blank controls, blind-scroll
controls, fresh draws, ablation, jitter. Not one of them measures whether the
killing is correct.

That is a real gap. A genuine ink signal could plausibly fail these tests:

  - per-scroll sign flips are physically possible, because partial-volume
    averaging can invert contrast between a 1.13 um scan and a 2.22 um one
  - a fresh-draw collapse can mean "real but narrow" rather than "false"
  - terms that score zero alone but work combined can be a genuine contrast
    that cancels a confound

Only the jitter test is hard to argue with. So a battery this aggressive needs
calibrating, or "we found nothing" is an untrustworthy sentence.

THE METHOD — SPIKE-IN RECOVERY

Take real tiles. Add a synthetic ink layer at the positions where the published
ink map says there IS ink, with a known contrast delta, spread over a
physically correct thickness (15 um, converted to layers per scan). Then run
the ordinary pipeline and see what delta is needed before it detects anything.

That yields a DETECTION FLOOR:

    the pipeline recovers synthetic ink at contrast >= X grey levels
    the real data shows nothing
    therefore any real ink contrast is below X

which is a quantitative negative result rather than an absence of a positive
one. It also states the sensitivity honestly for anyone reusing this code.

Two detectors are swept:
  matched   a high-pass of the depth-band image — nearly optimal for an
            injected intensity offset, so it bounds BEST-CASE sensitivity
  offaxis   the texture measure behind six of the eight top families, i.e.
            what the search would actually have to work with

Usage: python3 positive_control.py [n_tiles]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

_argv, sys.argv = sys.argv, [sys.argv[0]]
import nightshift as NS
sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "findings")

INK_UM = 15.0                       # the ink layer thickness
DELTAS = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]   # grey levels, 0-255


def inject(tile, delta):
    """Return a copy of the tile with a synthetic ink layer added.

    The ink map is at the downsampled grid, so it is expanded to volume
    coordinates by nearest-neighbour repeat. The layer is centred on the sheet
    peak and is INK_UM thick in physical units, so a fine scan gets many layers
    and a coarse scan gets one or two — which is the whole resolution story,
    reproduced honestly.
    """
    um, ds, pk = tile["um"], tile["ds"], tile["pk"]
    v = tile["vol8"]
    D, H, W = v.shape
    mask = (tile["ink"] > 128).astype(np.float32)
    iy, ix = tile["iy"], tile["ix"]
    step = max(1, int(round(ds)))
    sub = mask[iy:iy+int(np.ceil(H/step))+1, ix:ix+int(np.ceil(W/step))+1]
    if sub.size == 0:
        return None
    up = np.repeat(np.repeat(sub, step, 0), step, 1)[:H, :W]
    if up.shape != (H, W):
        pad = np.zeros((H, W), np.float32)
        pad[:up.shape[0], :up.shape[1]] = up
        up = pad
    nl = max(1, int(round(INK_UM/um)))
    a, b = max(0, pk-nl//2), min(D, pk+nl//2+1)
    out = v.astype(np.float32)
    out[a:b] += delta*up[None, :, :]
    new = dict(tile)
    new["vol8"] = np.clip(out, 0, 255).astype(np.uint8)
    return new


def detect_matched(tile):
    """High-pass of the depth-band image. Near-optimal for an added offset."""
    img = P.mid_image(tile, 8)
    return img - P.box(img, max(2, int(round(600.0/tile["um"]/2))))


def detect_offaxis(tile):
    img = P.mid_image(tile, 8)
    if (img > 0).mean() < 0.5:
        return None
    Pp = dict(scale_um=750.0, hp_um=160.0, proud_um=500.0, chan_um=200.0,
              chan_pct=70, plate_lo_um=100.0, plate_hi_um=500.0)
    return NS.make_features(img, tile["um"], Pp)["offaxis"]


DETECTORS = [("matched", detect_matched), ("offaxis", detect_offaxis)]


def main(n=8):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    rng = np.random.default_rng(31)
    cand = P.warm([held[i] for i in rng.permutation(len(held))[:n*3]], verbose=False)
    tiles = []
    for t in cand:
        c = P.crop_coverage(t)
        if c is not None and 0.03 < c < 0.6:
            tl = P.load_tile(t)
            if tl is not None:
                tiles.append(tl)
        if len(tiles) >= n:
            break
    print(f"{len(tiles)} tiles with real text\n")
    if not tiles:
        return

    contrast = float(np.median([np.percentile(P.mid_image(t, 8), 98) -
                                np.percentile(P.mid_image(t, 8), 2) for t in tiles]))
    print(f"median sheet contrast (p98-p2) = {contrast:.1f} grey levels")
    layers = ", ".join("{}:{}L".format(t["scroll"], max(1, int(round(INK_UM/t["um"]))))
                       for t in tiles[:4])
    print(f"synthetic ink layer = {INK_UM:.0f} um thick -> {layers}\n")

    rows = []
    for dname, fn in DETECTORS:
        print(f"--- detector: {dname} ---")
        print(f"{'delta':>7s} {'% of contrast':>14s} {'median r':>10s} {'signif':>8s}")
        for d in DELTAS:
            rs, ps = [], []
            for tile in tiles:
                mod = inject(tile, d) if d > 0 else tile
                if mod is None:
                    continue
                try:
                    f = fn(mod)
                except Exception:
                    continue
                if f is None:
                    continue
                s = P.score_vs_ink(f, mod, nulls=40)
                if s:
                    rs.append(abs(s["r"])); ps.append(s["p"])
            if len(rs) < 3:
                print(f"{d:7.2f} {'':>14s} {'too few':>10s}")
                continue
            m = float(np.median(rs))
            fr = float((np.array(ps) < 0.05).mean())
            rows.append(dict(detector=dname, delta=d, pct=100*d/contrast,
                             median_r=m, frac_signif=fr, n=len(rs)))
            print(f"{d:7.2f} {100*d/contrast:13.2f}% {m:10.3f} {fr*100:7.0f}%")
        print()

    json.dump(dict(sheet_contrast=contrast, ink_um=INK_UM, rows=rows),
              open(os.path.join(OUT, "positive_control.json"), "w"), indent=1)

    print("="*72)
    print("DETECTION FLOOR")
    print("="*72)
    for dname, _ in DETECTORS:
        rr = [r for r in rows if r["detector"] == dname]
        base = next((r["median_r"] for r in rr if r["delta"] == 0), 0.0)
        hit = next((r for r in rr if r["median_r"] >= max(0.25, base+0.15)), None)
        if hit:
            print(f"  {dname:8s} recovers synthetic ink at delta >= {hit['delta']:.2f} "
                  f"grey levels ({hit['pct']:.2f}% of sheet contrast), r={hit['median_r']:.3f}")
        else:
            print(f"  {dname:8s} never reached r>=0.25 even at delta={DELTAS[-1]:.0f} "
                  f"— this detector cannot recover ink at any tested amplitude")
    print(f"\n  baseline (delta=0, real data): "
          + ", ".join(f"{d} {next((r['median_r'] for r in rows if r['detector']==d and r['delta']==0), float('nan')):.3f}"
                      for d, _ in DETECTORS))
    print("\nRead this as: whatever contrast real Herculaneum ink has in these\n"
          "scans, it is below the floor above — because at that floor the\n"
          "pipeline DOES see it, and on the real data it does not.")
    return rows


if __name__ == "__main__":
    t0 = time.time()
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
    print(f"{time.time()-t0:.0f}s")
