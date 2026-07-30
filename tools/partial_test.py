"""Does partialling out sheet condition change the answer?

Compares, for each candidate feature, on held-out scrolls:

    raw     r(feature, ink)
    partial r(feature, ink | brightness, contrast, coherence, curvature)

and the same two on blank papyrus, where BOTH should be ~0.

The decisive comparison is the blank column. If partial correlation is doing
its job, a papyrus-condition detector's blank score collapses while a real ink
signal's held-out score survives. If everything collapses together, there was
never an ink signal to separate, and that is the finding.

Usage: python3 partial_test.py [n_tiles]
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

DEFAULTS = dict(scale_um=750.0, hp_um=160.0, proud_um=500.0, chan_um=200.0,
                chan_pct=70, plate_lo_um=100.0, plate_hi_um=500.0, depth_band=8)

CANDIDATES = ["offaxis", "hfenergy", "chandark", "sharp", "disorder",
              "pca_c1", "pca_c2", "pca_c3", "rti_height", "rti_specvar"]


def feature(tile, name):
    if name.startswith("pca_"):
        return DP.pca_features(tile).get(name)
    if name.startswith("rti_"):
        return RTI.rti_features(tile).get(name)
    img = P.mid_image(tile, DEFAULTS["depth_band"])
    if (img > 0).mean() < 0.5:
        return None
    return NS.make_features(img, tile["um"], DEFAULTS).get(name)


def main(n=12):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    rng = np.random.default_rng(11)
    pick = P.warm([held[i] for i in rng.permutation(len(held))[:n]], verbose=False)
    negs = P.warm(P.find_negatives(held, n=6), verbose=False)
    print(f"{len(pick)} held-out tiles, {len(negs)} blank-papyrus tiles\n")
    print(f"{'feature':13s} {'raw':>7s} {'partial':>8s} | "
          f"{'blank raw':>10s} {'blank part':>11s} | verdict")
    print("-"*72)

    rows = []
    for nm in CANDIDATES:
        def run(tiles, fn):
            out = []
            for t in tiles:
                tile = P.load_tile(t)
                if tile is None:
                    continue
                try:
                    f = feature(tile, nm)
                except Exception:
                    continue
                if f is None:
                    continue
                s = fn(f, tile)
                if s:
                    out.append(abs(s["r"]))
            return out

        hr = run(pick, P.score_vs_ink)
        hp = run(pick, P.score_partial)
        nr = run(negs, lambda f, t: P.score_vs_ink(f, t, require_cov=None))
        np_ = run(negs, lambda f, t: P.score_partial(f, t, require_cov=None))
        if len(hr) < 3 or len(hp) < 3:
            print(f"{nm:13s} too few tiles")
            continue
        m = lambda v: float(np.median(v)) if v else float("nan")
        row = dict(feature=nm, raw=m(hr), partial=m(hp),
                   blank_raw=m(nr), blank_partial=m(np_), n=len(hp))
        # a feature is only interesting if it SURVIVES partialling on ink
        # while its blank score dies
        survives = row["partial"] > 0.10 and row["blank_partial"] < 0.06
        row["survives"] = bool(survives)
        rows.append(row)
        print(f"{nm:13s} {row['raw']:7.3f} {row['partial']:8.3f} | "
              f"{row['blank_raw']:10.3f} {row['blank_partial']:11.3f} | "
              f"{'SURVIVES' if survives else 'dead'}")

    json.dump(rows, open(os.path.join(OUT, "partial_test.json"), "w"), indent=1)
    if rows:
        alive = [r for r in rows if r["survives"]]
        print("\n" + "="*72)
        if alive:
            print("SURVIVORS after removing sheet condition:")
            for r in alive:
                print(f"  {r['feature']}  partial |r|={r['partial']:.3f}  "
                      f"blank {r['blank_partial']:.3f}")
            print("\nThese are worth the forensic battery. Not a reading.")
        else:
            dr = np.median([r["raw"]-r["partial"] for r in rows])
            print("NOTHING survives partialling out sheet condition.")
            print(f"median drop from raw to partial: {dr:+.3f}")
            print("\nThat is the cleanest statement of the result so far: the\n"
                  "correlations these measures have with published ink are\n"
                  "explained by sheet brightness, contrast, fibre coherence and\n"
                  "curvature. Remove those and nothing is left. It is not that\n"
                  "the ink signal is weak — there is no separate ink signal in\n"
                  "these measures at all.")
    return rows


if __name__ == "__main__":
    t0 = time.time()
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
    print(f"\n{time.time()-t0:.0f}s")
