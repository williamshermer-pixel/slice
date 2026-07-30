"""COLUMN — stop flattening. Use each pixel's depth profile as a profile.

THE ADMISSION THIS FILE EXISTS TO FIX

Almost every feature in this project begins with `P.mid_image()` — a mean over a
depth band, producing ONE 2D picture — and everything afterwards is a 2D texture
filter. Of ~29 features, only the PCA projections and the tail counts touch the
depth stack at all, and both reduce it immediately.

So the pipeline has been: take a depth-resolved subvolume, throw the depth away,
then hunt for a surface phenomenon in what is left. The build brief says the
opposite in its second sentence: the model must see a depth-resolved subvolume,
not one flattened slice.

WHAT A DEPTH COLUMN ACTUALLY CONTAINS

For each (y, x) the volume holds a profile through the sheet: air, then the rise
into papyrus, a body, then the fall back to air. Two faces. Measured label-free
across the corpus, the faces sit around -15..-9 and +6..+18 layers from the
intensity peak, giving sheet windows of 41-75 um.

Ink is applied TO A FACE and, per Mocella et al., does not fully penetrate the
fibres. So if it is anywhere in this data it is a perturbation of the profile AT
the face:

  shoulder    extra material just OUTSIDE the face — ink sitting on top
  sharpness   how abruptly the profile rises — ink blunts or sharpens the edge
  face_shift  the face displaced outward where ink adds thickness
  asymmetry   the two faces differ; ink is on one side (the recto)

Every one of these is a property of the COLUMN and is destroyed by averaging the
band into an image. None of them has been measured in this project.

IMPORTANT: the face is located PER PIXEL, not globally. A single global offset is
what the brief warns against — the sheet warps, so a fixed layer wanders off the
surface and smears the signal. Here each column finds its own face.

Usage: python3 column.py [n_tiles]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "findings")

DEFAULT = dict(
    span=20,          # layers each side of the peak to consider
    smooth=1.5,       # profile smoothing, in layers
    side="both",      # which face: "neg", "pos", "both"
    shoulder=3,       # layers outside the face to integrate for the shoulder
)


def _columns(tile, span):
    """The depth stack as float32, [D, H, W], centred on the sheet peak."""
    pk = tile["pk"]
    nz = tile["vol8"].shape[0]
    a, b = max(0, pk-span), min(nz, pk+span+1)
    v = P.layers(tile, a, b)
    return v, pk - a


_cache = {}


def _decompose(tile, span, smooth):
    """The expensive per-tile work: smoothed stack, gradient, per-pixel faces.

    Cached, because the search re-evaluates the same tile thousands of times
    with different downstream parameters and none of them change this part.
    Without the cache a column feature costs 5.6 s per tile and is unusable
    inside the pack.
    """
    key = (tile["seg"], int(span), float(smooth))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    v, c = _columns(tile, int(span))
    if v.shape[0] < 9:
        _cache[key] = None
        return None
    k = max(1, int(round(float(smooth))))
    if k > 1:
        from scipy.ndimage import uniform_filter1d
        v = uniform_filter1d(v, size=2*k+1, axis=0, mode="nearest")
    g = np.gradient(v, axis=0)
    f_neg = np.argmax(g[:c], axis=0).astype(np.int32)
    f_pos = (np.argmin(g[c:], axis=0) + c).astype(np.int32)
    s_neg = np.max(g[:c], axis=0)
    s_pos = -np.min(g[c:], axis=0)
    body = np.maximum(v.mean(0), 1e-6)
    out = dict(v=v, c=c, f_neg=f_neg, f_pos=f_pos, s_neg=s_neg, s_pos=s_pos,
               body=body, D=v.shape[0])
    if len(_cache) > 48:
        _cache.clear()
    _cache[key] = out
    return out


def column_features(tile, p=None):
    """Per-pixel properties of the depth profile, with the face found per pixel."""
    p = dict(DEFAULT, **(p or {}))
    d = _decompose(tile, p["span"], p["smooth"])
    if d is None:
        return {}
    v, D, body = d["v"], d["D"], d["body"]
    f_neg, f_pos = d["f_neg"], d["f_pos"]
    sh = int(p["shoulder"])

    def at(idx):
        # take_along_axis, not meshgrid fancy-indexing: no giant index arrays
        i = np.clip(idx, 0, D-1)[None, :, :]
        return np.take_along_axis(v, i, axis=0)[0]

    out_neg = at(f_neg - sh)
    in_neg = at(f_neg + sh)
    out_pos = at(f_pos + sh)

    return {
        "col_shoulder_neg": out_neg/body,
        "col_shoulder_pos": out_pos/body,
        "col_sharp_neg": d["s_neg"]/body,
        "col_sharp_pos": d["s_pos"]/body,
        "col_face_neg": f_neg.astype(np.float32) - float(np.median(f_neg)),
        "col_face_pos": f_pos.astype(np.float32) - float(np.median(f_pos)),
        "col_thick": (f_pos - f_neg).astype(np.float32),
        "col_asym": (out_neg - out_pos)/body,
        "col_rise": (in_neg - out_neg)/body,
    }


COLUMN_NAMES = ["col_shoulder_neg", "col_shoulder_pos", "col_sharp_neg",
                "col_sharp_pos", "col_face_neg", "col_face_pos", "col_thick",
                "col_asym", "col_rise"]


def main(n=12):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blindp = [t for s in bs for t in by[s]]

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
    tiles = grab(held, 777, n)
    blind = grab(blindp, 0, 6)
    negs = [P.load_tile(t) for t in P.warm(P.find_negatives(held, n=8), verbose=False)]
    negs = [t for t in negs if t is not None]
    print(f"{len(tiles)} held-out, {len(negs)} verified-blank, {len(blind)} blind\n")
    if len(tiles) < 4:
        print("not enough tiles"); return

    print("Depth-column features. AUC, with the spatial null and the blind control.")
    print("The blind scroll is the one that matters: its ink was never sampled.\n")
    print(f"{'feature':18s} {'AUC':>7s} {'null':>7s} {'excess':>8s} {'blind':>7s}   verdict")
    print("-"*66)
    rows = []
    for nm in COLUMN_NAMES:
        a, nu, ps = [], [], []
        for tl in tiles:
            f = column_features(tl).get(nm)
            if f is None:
                continue
            s = P.auc_vs_ink(f, tl, nulls=40)
            if s:
                a.append(s["auc"]); ps.append(s["p"])
                if s["null_median"]:
                    nu.append(s["null_median"])
        if len(a) < 4:
            print(f"{nm:18s} too few tiles"); continue
        am, nm_ = float(np.median(a)), (float(np.median(nu)) if nu else 0.5)
        ba = []
        for tl in blind:
            f = column_features(tl).get(nm)
            if f is None:
                continue
            s = P.auc_vs_ink(f, tl, nulls=1)
            if s:
                ba.append(s["auc"])
        bm = float(np.median(ba)) if ba else None
        exc = am - nm_
        alive = exc >= 0.09 and am >= 0.66 and (bm is None or bm <= 0.58)
        rows.append(dict(feature=nm, auc=am, null=nm_, excess=exc, blind=bm,
                         n=len(a), alive=bool(alive)))
        print(f"{nm:18s} {am:7.3f} {nm_:7.3f} {exc:+8.3f} "
              f"{('%.3f' % bm) if bm else '--':>7s}   "
              f"{'*** WORTH THE BATTERY ***' if alive else 'dead'}")

    json.dump(rows, open(os.path.join(OUT, "column_test.json"), "w"), indent=1)
    alive = [r for r in rows if r["alive"]]
    print()
    if alive:
        print("First depth-column features to clear the screen. Next: scorecard.py\n"
              "then verify.py. Nothing is a finding until it survives both.")
    else:
        print("Nothing clears. But note these measure the PROFILE, which no\n"
              "previous feature did — so this is a genuinely new negative rather\n"
              "than another texture statistic restating the last fourteen.")
    print(f"{time.time()-t0:.0f}s")
    return rows


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
