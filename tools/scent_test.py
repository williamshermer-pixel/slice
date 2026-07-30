"""Does the physics bank see anything the level bank structurally could not?

Scores the five scent features against published ink on held-out scrolls, with
the verified-blank control and the blind-scroll physics control, plus partial
correlation with sheet condition removed.

The interesting outcome is not a big raw number. It is a feature whose PARTIAL
correlation survives while its blank score stays near zero, because that is the
combination no level-based feature has ever produced here.

`speckdepth` is worth watching separately. It measures how tightly bright
specks cluster at the sheet face, which is a statement about where ink was
physically applied and uses no label at any point.

Usage: python3 scent_test.py [n_tiles]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P
import scent as SC

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "findings")


def main(n=12):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blind_pool = [t for s in bs for t in by[s]]
    rng = np.random.default_rng(11)

    cand = P.warm([held[i] for i in rng.permutation(len(held))[:n*2]], verbose=False)
    tiles = []
    for t in cand:
        c = P.crop_coverage(t)
        if c is not None and 0.02 < c < 0.7:
            tl = P.load_tile(t)
            if tl is not None:
                tiles.append(tl)
        if len(tiles) >= n:
            break
    negs = [P.load_tile(t) for t in P.warm(P.find_negatives(held, n=8), verbose=False)]
    negs = [t for t in negs if t is not None]
    blind = [P.load_tile(t) for t in P.warm(
        [blind_pool[i] for i in np.random.default_rng(0).permutation(len(blind_pool))[:5]],
        verbose=False)]
    blind = [t for t in blind if t is not None]
    print(f"{len(tiles)} text tiles, {len(negs)} verified-blank, {len(blind)} blind\n")
    if len(tiles) < 4:
        print("not enough tiles"); return

    print(f"{'feature':12s} {'ink r':>8s} {'signif':>7s} {'partial':>8s} "
          f"{'blank':>7s} {'blind':>7s}   verdict")
    print("-"*68)
    rows = []
    for nm in SC.SCENT_NAMES:
        rs, ps, pr = [], [], []
        for tile in tiles:
            F = SC.scent_features(tile)
            f = F.get(nm)
            if f is None:
                continue
            s = P.score_vs_ink(f, tile, nulls=40)
            if s:
                rs.append(s["r"]); ps.append(s["p"])
            sp = P.score_partial(f, tile, nulls=12)
            if sp:
                pr.append(abs(sp["r"]))
        if len(rs) < 4:
            print(f"{nm:12s} too few tiles")
            continue
        rs = np.array(rs)
        sign = 1.0 if np.median(rs) > 0 else -1.0
        med = float(np.median(sign*rs))
        nb = P.neg_control(lambda tl, _n=nm: SC.scent_features(tl).get(_n), negs)
        bl = []
        for tile in blind:
            f = SC.scent_features(tile).get(nm)
            if f is None:
                continue
            s = P.score_vs_ink(f, tile, nulls=1)
            if s:
                bl.append(abs(s["r"]))
        blm = float(np.median(bl)) if bl else None
        prm = float(np.median(pr)) if pr else None
        alive = (abs(med) >= 0.20 and prm is not None and prm >= 0.15
                 and (nb is None or nb <= 0.12) and (blm is None or blm <= 0.15))
        rows.append(dict(feature=nm, ink_r=med, frac_signif=float((np.array(ps) < 0.05).mean()),
                         partial=prm, blank=nb, blind=blm, n=len(rs), alive=bool(alive)))
        g = lambda x: "--" if x is None else f"{x:.3f}"
        print(f"{nm:12s} {med:+8.3f} {float((np.array(ps)<0.05).mean())*100:6.0f}% "
              f"{g(prm):>8s} {g(nb):>7s} {g(blm):>7s}   "
              f"{'WORTH THE BATTERY' if alive else 'dead'}")

    json.dump(rows, open(os.path.join(OUT, "scent_test.json"), "w"), indent=1)
    print()
    alive = [r for r in rows if r["alive"]]
    if alive:
        print("These are the first physics-grounded features to clear the screen:")
        for r in alive:
            print(f"  {r['feature']}  ink {r['ink_r']:+.3f}  partial {r['partial']:.3f}  "
                  f"blank {r['blank']}  blind {r['blind']}")
        print("\nNext: tools/verify.py on each. Nothing is a finding until it\n"
              "survives a fresh draw, per-scroll breakdown, ablation and jitter.")
    else:
        print("Nothing clears the screen. If the bit-depth hypothesis in\n"
              "findings/ink-physics.md is right, that is expected: the ink\n"
              "contrast would sit below one 8-bit quantisation step, and no\n"
              "feature computed on these arrays can recover it.")
    return rows


if __name__ == "__main__":
    t0 = time.time()
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
    print(f"{time.time()-t0:.0f}s")
