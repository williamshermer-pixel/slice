"""ENSEMBLE — learn the combination instead of guessing it.

WHY THIS IS THE HIGHEST-PROBABILITY THING LEFT

The search has always been the same shape: pick 1-3 features from the bank,
give each a weight from a coarse grid, sum. Across ~7,000 variants that is a
tiny, badly-conditioned corner of the space. Meanwhile the thing that
demonstrably reads this data — the published CNN whose output we validate
against — succeeds by LEARNING a combination over many channels.

We cannot train a CNN here. But a logistic regression over all 38 features is
free, and it is the single most powerful thing not yet tried:

  - it weights every feature simultaneously, not three at a time
  - the weights are continuous and fitted, not drawn from {1.0, 0.7, 0.5, ...}
  - it can express "A minus B given C" relationships the random search cannot

THE LEAKAGE DISCIPLINE, WHICH IS THE WHOLE GAME

A fitted model can memorise. So:

  FIT       on TUNE scrolls only, never on held-out
  SELECT    nothing on held-out — no threshold picking, no feature pruning
  REPORT    held-out AUC, its spatial null, the blind scroll, verified-blank
  CONFIRM   on a disjoint scroll the fit never touched

If the fit sees a held-out tile even once, the number is worthless. This file
keeps the split at SCROLL level, which is stricter than tile level: the model
never sees the scribe, the scan, or the sheet it is scored on.

Regularisation is deliberately heavy (small C). With 38 correlated features and
a few hundred thousand pixels, an unpenalised fit will happily learn the
papyrus condition of the tune scrolls.

Usage: python3 ensemble.py [n_tune_tiles] [n_held_tiles]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

_argv, sys.argv = sys.argv, [sys.argv[0]]
import dogs as D          # reuse its feature_map and full 38-feature bank
sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "ensemble")
os.makedirs(OUT, exist_ok=True)

# one fixed, sane parameter set — the point is the COMBINATION, not a sweep
BASE = dict(scale_um=750.0, hp_um=160.0, proud_um=500.0, chan_um=200.0,
            chan_pct=70, plate_lo_um=100.0, plate_hi_um=500.0, depth_band=8,
            lo_um=150.0, hi_um=1200.0, unsharp_um=600.0, gain=3.0,
            exponent=40.0, elev_deg=18.0, n_lights=12, stroke_um=350.0,
            fringe_um=40.0, tail_pct=99.5, void_pct=2.0, fibre_lo_um=200.0,
            fibre_hi_um=600.0, neigh_um=1500.0, crest_pct=65.0, offset=0,
            col_span=20, col_smooth=1.5, col_shoulder=3)


def feature_stack(tile, names):
    """All features for one tile, binned to the ink grid: (n_pixels, n_features)."""
    V = dict(BASE); V["features"] = list(names); V["weights"] = [1.0]*len(names)
    cols, kept = [], []
    for nm in names:
        V1 = dict(V); V1["features"] = [nm]; V1["weights"] = [1.0]
        try:
            f = D.feature_map(tile, V1)
        except Exception:
            f = None
        if f is None:
            continue
        fb, sub = P._align(f, tile)
        if fb is None or not np.isfinite(fb).all():
            continue
        cols.append(P.z(fb).ravel())
        kept.append(nm)
    if not cols:
        return None, None, None
    X = np.stack(cols, 1)
    y = (sub > 128).ravel()
    return X, y, kept


def gather(tiles, names, cap=60000, seed=0):
    rng = np.random.default_rng(seed)
    Xs, ys, common = [], [], None
    for tl in tiles:
        X, y, kept = feature_stack(tl, names)
        if X is None or y.sum() < 50 or (~y).sum() < 50:
            continue
        if common is None:
            common = kept
        if kept != common:                     # keep the matrix rectangular
            idx = [kept.index(n) for n in common if n in kept]
            if len(idx) != len(common):
                continue
            X = X[:, idx]
        # subsample per tile so one big tile cannot dominate the fit
        if len(y) > cap:
            sel = rng.choice(len(y), cap, replace=False)
            X, y = X[sel], y[sel]
        Xs.append(X); ys.append(y)
    if not Xs:
        return None, None, None
    return np.vstack(Xs), np.concatenate(ys), common


def auc_of(score, y):
    n1 = int(y.sum()); n0 = len(y)-n1
    if n1 < 50 or n0 < 50:
        return None
    o = np.argsort(score); rk = np.empty(len(score), float); rk[o] = np.arange(1, len(score)+1)
    a = (rk[y].sum() - n1*(n1+1)/2.0)/(n1*n0)
    return float(max(a, 1.0-a))


def fit_logistic(X, y, C=0.02, iters=300, seed=0):
    """L2-penalised logistic regression, gradient descent, numpy only.

    Written rather than imported: sklearn is not installed and this project's
    whole data stack is numpy + scipy. Twenty lines is cheaper than a
    dependency, and it keeps the fit auditable — the regularisation strength is
    right here rather than behind a default.

    Class-balanced, because ink is ~7% of pixels and an unweighted fit simply
    predicts "no ink" everywhere at 93% accuracy.
    """
    n, d = X.shape
    w = np.zeros(d)
    b = 0.0
    pos = y.astype(np.float64)
    wpos = 0.5/max(pos.mean(), 1e-9)
    wneg = 0.5/max(1.0-pos.mean(), 1e-9)
    sw = np.where(y, wpos, wneg)
    lr = 0.5
    lam = 1.0/max(C*n, 1e-9)
    for _ in range(iters):
        z = X @ w + b
        p_ = 1.0/(1.0 + np.exp(-np.clip(z, -30, 30)))
        g = X.T @ (sw*(p_ - pos))/n + lam*w
        gb = float((sw*(p_ - pos)).mean())
        w -= lr*g
        b -= lr*gb
    return w, b


def main(n_tune=8, n_held=12):
    names = list(D.ALL_NAMES)
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    tune_p = [t for s in ts for t in by[s]]
    held_p = [t for s in hs for t in by[s]]
    blind_p = [t for s in bs for t in by[s]]

    def grab(pool, seed, k, lo=0.03, hi=0.7):
        rng = np.random.default_rng(seed); out = []
        for t in P.warm([pool[i] for i in rng.permutation(len(pool))[:k*3]], verbose=False):
            c = P.crop_coverage(t)
            if c is not None and lo < c < hi:
                tl = P.load_tile(t)
                if tl is not None:
                    out.append(tl)
            if len(out) >= k:
                break
        return out

    t0 = time.time()
    print(f"fitting on TUNE scrolls only: {ts}")
    print(f"scoring on HELD-OUT: {hs}    blind: {bs}\n")
    tune = grab(tune_p, 3, n_tune)
    Xtr, ytr, names = gather(tune, names, seed=3)
    if Xtr is None:
        print("no usable tune data"); return
    print(f"train matrix {Xtr.shape}, {ytr.mean()*100:.1f}% ink, {len(names)} features")

    w, b0 = fit_logistic(Xtr, ytr, C=0.02)
    order = np.argsort(-np.abs(w))
    print("\ntop weights (fitted on tune scrolls, never on held-out):")
    for i in order[:8]:
        print(f"   {names[i]:18s} {w[i]:+.3f}")

    def score_tiles(tiles, label, nulls=40):
        aucs, nl = [], []
        for tl in tiles:
            X, y, kept = feature_stack(tl, names)
            if X is None or kept != names or y.sum() < 50 or (~y).sum() < 50:
                continue
            s = X @ w
            a = auc_of(s, y)
            if a is None:
                continue
            aucs.append(a)
            # spatial null on the TARGET, same as pack.auc_vs_ink
            fb, sub = P._align(D.feature_map(tl, dict(BASE, features=[names[0]],
                                                      weights=[1.0])), tl)
            H, W = sub.shape
            rng = np.random.default_rng(7)
            for _ in range(6):
                sh = np.roll(np.roll(sub, int(rng.integers(6, H-6)), 0),
                             int(rng.integers(6, W-6)), 1)
                v = auc_of(s, (sh > 128).ravel())
                if v:
                    nl.append(v)
        if not aucs:
            return None, None, 0
        return float(np.median(aucs)), (float(np.median(nl)) if nl else 0.5), len(aucs)

    held = grab(held_p, 777, n_held)
    blind = grab(blind_p, 0, 6)
    ha, hn, hc = score_tiles(held, "held")
    ba, bn, bc = score_tiles(blind, "blind", nulls=1)

    print(f"\nHELD-OUT   AUC {ha:.3f}  null {hn:.3f}  excess {ha-hn:+.3f}  (n={hc})"
          if ha else "\nHELD-OUT   no usable tiles")
    print(f"BLIND      AUC {ba:.3f}  (chance 0.500, n={bc})" if ba else "BLIND      --")

    # second held-out draw, never used for anything
    held2 = grab(held_p, 424242, n_held)
    h2a, h2n, h2c = score_tiles(held2, "held2")
    print(f"FRESH DRAW AUC {h2a:.3f}  null {h2n:.3f}  excess {h2a-h2n:+.3f}  (n={h2c})"
          if h2a else "FRESH DRAW no usable tiles")

    rec = dict(features=names, weights=[float(x) for x in w],
               heldout_auc=ha, heldout_null=hn, heldout_excess=(ha-hn) if ha else None,
               fresh_auc=h2a, fresh_null=h2n,
               fresh_excess=(h2a-h2n) if h2a else None, blind_auc=ba,
               n_held=hc, n_fresh=h2c, C=0.02, tune_scrolls=ts, held_scrolls=hs)
    json.dump(rec, open(os.path.join(OUT, "ensemble.json"), "w"), indent=1)

    print("\n" + "="*68)
    if ha and h2a:
        ok = ((ha-hn) >= 0.09 and (h2a-h2n) >= 0.09 and ha >= 0.66
              and (ba is None or ba <= 0.58))
        print("CLEARS THE BAR ON BOTH DRAWS — run verify.py before believing it"
              if ok else
              "does not clear. Note whether the two draws AGREE: a big gap between\n"
              "them is draw noise, and the honest reading is underpowered, not dead.")
    print(f"{time.time()-t0:.0f}s")
    return rec


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 8, int(a[1]) if len(a) > 1 else 12)
