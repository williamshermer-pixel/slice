#!/usr/bin/env python3
"""Is the silent sheet actually blank, or is its ink sitting under their cutoff?

THE SETUP. PHerc0343P band b2 is a run of consecutive windings: -5 -4 -3 -2 -1
0 +1. Measured 3D nearest-neighbour gaps between consecutive wraps are ~40-70
voxels at 2.215 um (roughly one papyrus thickness), and the gap grows
monotonically with wrap separation, so the numbering is real wrap order.

Two of those wraps are SILENT in absolute terms (-3 and -1: their maps' top 1%
never reaches 200/255) while the wraps touching them on both sides carry ink. A
scribe does not write, skip one turn of the scroll, and resume. So either the
model failed on -1, or something about that sheet's geometry defeats it.

THE JOIN IS EXACT, WHICH IS THE WHOLE REASON THIS IS CHEAP. The tifxyz mesh
grid is the surface canvas / 20 (verified: canvas 9120x13040, mesh 456x652) and
the published ds8 map is the canvas / 8. So mesh cell -> map pixel is a pure
x2.5, and 3D position is known for every mesh cell. No registration.

TWO QUESTIONS, KEPT APART
-------------------------
  A. Does -1 have letter-scale structure of its own, below their cutoff?
     Tested against a rolled spatial null, which preserves the map's histogram
     and autocorrelation while destroying its registration to the papyrus.

  B. Is -1's score elevated where its NEIGHBOURS are inked, at the same 3D
     point? A positive here is ambiguous and must not be reported as discovery:
     ~100 um of separation is well within bleed-through range, so the honest
     reading of a positive is "the model on -1 is seeing the neighbour's ink",
     not "-1 has text in the same place". Consecutive wraps are a full turn
     apart along the strip and carry DIFFERENT columns, so genuine text on -1
     has no reason to correlate positionally with text on 0.

Reported separately, and B is labelled as a confound rather than a finding.

    python3 tools/sandwich_0343p.py
"""
import io
import json
import os
import pickle
import urllib.request

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
UA = {"User-Agent": "Mozilla/5.0"}
OUT = os.path.join(ROOT, "out", "sandwich_0343p")
CATALOG = os.path.join(ROOT, "public", "ink-maps.json")

VOL = "20260304131111-2.215um"
BAND = {
    "-4": "20250902170441--4_b2",
    "-3": "20250902170447--3_b2",
    "-2": "20250902171202--2_b2",
    "-1": "20250902171204--1_b2",
    "0": "20250904233748-0_b2",
    "+1": "20250905172054-1_b2",
}
SILENT = {"-3", "-1"}
N_ROLL = 24
MESH_PER_CANVAS = 20      # tifxyz grid = canvas / 20
MAP_PER_CANVAS = 8        # published ds8 = canvas / 8


def fetch(url, timeout=300):
    os.makedirs(os.path.join(OUT, "cache"), exist_ok=True)
    p = os.path.join(OUT, "cache", url.rsplit("/", 3)[-1].replace("/", "_")
                     + "_" + str(abs(hash(url)) % 10**8))
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return open(p, "rb").read()
    d = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()
    open(p, "wb").write(d)
    return d


def load_mesh(seg):
    import tifffile
    sid = seg.split("-")[0]
    base = f"{B}/PHerc0343P/segments/{seg}/mesh/{sid}-on-{VOL}.tifxyz"
    a = [tifffile.imread(io.BytesIO(fetch(f"{base}/{ax}.tif"))).astype(np.float32)
         for ax in "xyz"]
    xyz = np.stack(a, -1)
    valid = (xyz != 0).any(-1)
    return xyz, valid


def load_map(seg_full):
    doc = json.load(open(CATALOG))
    e = next(x for x in doc["entries"]
             if x["scroll"] == "PHerc0343P" and x["segment"] == seg_full)
    a = np.array(Image.open(io.BytesIO(fetch(e["maps"][0]["url"]))))
    if a.ndim == 3:
        a = a[..., 0]
    return a, e


def map_at_mesh(mapping, mesh_shape):
    """Sample the ds8 map on the mesh grid: mesh cell -> canvas -> map px."""
    h, w = mesh_shape
    r = (np.arange(h) * MESH_PER_CANVAS / MAP_PER_CANVAS).astype(int)
    c = (np.arange(w) * MESH_PER_CANVAS / MAP_PER_CANVAS).astype(int)
    r = np.clip(r, 0, mapping.shape[0] - 1)
    c = np.clip(c, 0, mapping.shape[1] - 1)
    return mapping[np.ix_(r, c)]


def auc(pos, neg):
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    a = np.concatenate([pos, neg])
    order = a.argsort()
    ranks = np.empty(len(a), float)
    ranks[order] = np.arange(1, len(a) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]
    rp = ranks[:len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(20260801)
    mesh, mp, ent = {}, {}, {}
    for k, seg in BAND.items():
        xyz, valid = load_mesh(seg)
        m, e = load_map(seg)
        mesh[k] = (xyz, valid)
        ent[k] = e
        mp[k] = map_at_mesh(m, valid.shape)
        on = m[m > 0]
        print(f"{k:3s} mesh {valid.shape} map {m.shape} "
              f"p99={int(np.percentile(on,99)):3d} "
              f"{'SILENT' if k in SILENT else ''}")

    results = {}
    for target in ("-1", "-3"):
        xyz, valid = mesh[target]
        s = mp[target].astype(float)
        on = valid & (s > 0)
        print(f"\n=== target {target} ({BAND[target]})  {on.sum():,} live cells")

        # -------- A. structure of its own, below their cutoff -----------------
        # Their publication bar is 200. Look only under it, so nothing here can
        # be a call they already made.
        sub = np.where(s < 200, s, 0.0)
        lab, n = ndimage.label(sub >= np.percentile(sub[on], 99))
        real_big = 0
        if n:
            areas = ndimage.sum(np.ones_like(lab, bool), lab, range(1, n + 1))
            real_big = int((areas >= 4).sum())
        null_big = []
        for _ in range(N_ROLL):
            dy = int(rng.integers(sub.shape[0] // 8, sub.shape[0] - sub.shape[0] // 8))
            dx = int(rng.integers(sub.shape[1] // 8, sub.shape[1] - sub.shape[1] // 8))
            r = np.roll(np.roll(sub, dy, 0), dx, 1)
            l2, n2 = ndimage.label(r >= np.percentile(r[on], 99))
            if n2:
                a2 = ndimage.sum(np.ones_like(l2, bool), l2, range(1, n2 + 1))
                null_big.append(int((a2 >= 4).sum()))
            else:
                null_big.append(0)
        null_big = np.array(null_big)
        pA = float((null_big >= real_big).sum() + 1) / (N_ROLL + 1)
        print(f"  A. own sub-threshold clusters: {real_big} vs null "
              f"{null_big.mean():.1f}+-{null_big.std():.1f}  p={pA:.3f}")

        # -------- B. neighbour ink at the same 3D point (CONFOUND) ------------
        pts = xyz[on]
        neigh = {}
        for nb in ("-2", "0") if target == "-1" else ("-4", "-2"):
            nxyz, nvalid = mesh[nb]
            nmap = mp[nb].astype(float)
            nlive = nvalid & (nmap > 0)
            tree = cKDTree(nxyz[nlive])
            d, idx = tree.query(pts, workers=-1)
            nb_score = nmap[nlive][idx]
            close = d < 120                    # within ~one wrap gap
            bar = np.percentile(nmap[nlive], 90)
            inked = close & (nb_score >= bar)
            blank = close & (nb_score < np.percentile(nmap[nlive], 50))
            mine = s[on]
            a = auc(mine[inked], mine[blank])
            # rolled null: same test with our own scores shuffled spatially
            nulls = []
            for _ in range(N_ROLL):
                dy = int(rng.integers(s.shape[0] // 8, s.shape[0] - s.shape[0] // 8))
                dx = int(rng.integers(s.shape[1] // 8, s.shape[1] - s.shape[1] // 8))
                rs = np.roll(np.roll(s, dy, 0), dx, 1)[on]
                nulls.append(auc(rs[inked], rs[blank]))
            nulls = np.array([x for x in nulls if np.isfinite(x)])
            pB = float((nulls >= a).sum() + 1) / (len(nulls) + 1)
            neigh[nb] = dict(auc=round(a, 4),
                             null_mean=round(float(nulls.mean()), 4),
                             p=round(pB, 3),
                             n_inked=int(inked.sum()), n_blank=int(blank.sum()),
                             median_gap_vox=round(float(np.median(d)), 1))
            print(f"  B. vs {nb:3s} neighbour-inked AUC {a:.3f} "
                  f"(null {nulls.mean():.3f}) p={pB:.3f} "
                  f"n={int(inked.sum())}/{int(blank.sum())} "
                  f"gap {np.median(d):.0f} vox")
        results[target] = dict(
            segment=BAND[target], live_cells=int(on.sum()),
            own_structure=dict(clusters=real_big,
                               null_mean=round(float(null_big.mean()), 2),
                               p=round(pA, 3)),
            neighbour_confound=neigh)

    doc = dict(
        scroll="PHerc0343P", band="b2", rolls=N_ROLL,
        note="A tests whether a silent sheet has letter-scale structure of its "
             "own BELOW Vesuvius Challenge's publication bar of 200. B tests "
             "whether its scores rise where a touching wrap is inked; a "
             "positive there is most likely BLEED-THROUGH across ~100 um, not "
             "text, because consecutive wraps carry different columns. No ink "
             "is claimed by this tool.",
        results=results)
    p = os.path.join(OUT, "sandwich.json")
    json.dump(doc, open(p, "w"), indent=1)
    print(f"\n-> {p}")


if __name__ == "__main__":
    main()
