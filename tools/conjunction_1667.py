#!/usr/bin/env python3
"""Conjunction search on PHerc1667 — using two independent scans to gain
SENSITIVITY, not just to filter.

The cross-energy pair is usually thought of as a check: does the second scan
confirm the first. But two independent measurements of the same papyrus also
average down independent noise. A mark too faint to clear either detector's
threshold alone can clear a JOINT threshold, because the noise is independent
and the ink is not. That is the only way this project has found to look for ink
that neither published map reports, without a GPU and without a new model.

The statistic is min(z59, z78) over a letter-sized box, computed only on sheet
that BOTH scans cover and that NEITHER calls (plus a fixed 1.5 mm keep-out from
any call — the model blend kernel smears past a letter's called extent, and a
keep-out proportional to the hand would be the wrong shape).

min() rather than sum() on purpose: a sum lets one scan's artifact carry a spot
on its own, which is the failure mode this whole design exists to prevent. min
requires BOTH scans to be independently elevated.

WHAT THIS DESIGN CANNOT RULE OUT, stated up front: sheet CONDITION. Text sits
on well-preserved papyrus, so preservation correlates with "text here", and
both energies respond to it — a shared cause, not independent noise. Rolling
one map destroys registration but not condition, so the null below does not
separate ink from condition. Two things push back on it and neither is
conclusive: the letter-scale high-pass removes smooth preservation gradients,
and real text lies in rows at a fixed pitch while condition does not. The
render is the arbiter. Any survivor here is a CANDIDATE, not a reading.

    python3 tools/conjunction_1667.py [segment]
"""
import os, sys, glob, json
import numpy as np
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc1667")
if SCROLL not in HANDS:
    raise SystemExit(f"no cross-energy pair / measured hand for {SCROLL}; "
                     f"known: {list(HANDS)}")
_DIRS = {"PHerc1667": "s1667"}
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))

DS8_UM = 18.064
LETTER_MM = HANDS[SCROLL]
LETTER_PX = LETTER_MM * 1000.0 / DS8_UM        # ~90 px
BOX = max(3, int(round(0.7 * LETTER_PX)))
KEEPOUT_MM = 1.5                               # blend kernel, a FIXED distance
KEEPOUT_PX = int(round(KEEPOUT_MM * 1000.0 / DS8_UM))
NULL_N = int(os.environ.get("NULL_N", 24))   # raise to resolve p below the 1/(N+1) floor
TOPK = int(os.environ.get("TOPK", 8))                                        # survivors examined per segment


MIN_BOX_COVER = 0.95      # a letter-box must be ~entirely on shared sheet


def letter_box(a, m):
    """Letter-box mean over shared sheet.

    den > 0.5 was too permissive: it lets a box sit half off-sheet and still
    report a value, dividing a partial sum by a small denominator. That is
    unstable exactly at the sheet boundary, and it manufactured this project's
    first cross-energy candidate — 0.78 mm from the edge, under half a letter,
    with 60.6% of the whole search area lying within two letters of a boundary.
    Require the box to be essentially all sheet instead."""
    a = np.where(m, a, 0.0)
    num = ndimage.uniform_filter(a, BOX)
    den = ndimage.uniform_filter(m.astype(np.float32), BOX)
    return np.where(den >= MIN_BOX_COVER, num / np.maximum(den, 1e-6), 0.0)


def interior(m, letters=1.5):
    """Shared sheet eroded away from its own boundary, so no scored pixel has
    a letter-box hanging off the edge. A FIXED physical distance, like the
    spillover keep-out — the edge instability is a property of the box, not of
    the hand."""
    d = ndimage.distance_transform_edt(m)
    return m & (d >= max(BOX / 2.0 + 2, letters * LETTER_PX))


def zmap(a, m, search):
    """Letter-scale high-pass, then z-score against the SEARCH region only, so
    the called text does not set the scale it is being compared against."""
    hp = a - ndimage.gaussian_filter(np.where(m, a, 0.0), LETTER_PX)
    L = letter_box(hp, m)
    v = L[search]
    if v.size < 100 or v.std() < 1e-9:
        return None
    return (L - v.mean()) / v.std()


def peaks(J, search, k, min_sep):
    """Top-k local maxima of J inside search, separated by min_sep."""
    out = []
    work = np.where(search, J, -np.inf)
    for _ in range(k):
        i = np.unravel_index(np.argmax(work), work.shape)
        if not np.isfinite(work[i]):
            break
        out.append((float(work[i]), int(i[0]), int(i[1])))
        y0, y1 = max(0, i[0] - min_sep), min(work.shape[0], i[0] + min_sep)
        x0, x1 = max(0, i[1] - min_sep), min(work.shape[1], i[1] + min_sep)
        work[y0:y1, x0:x1] = -np.inf
    return out


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    rng = np.random.default_rng(7)
    report = {}

    for f in sorted(glob.glob(os.path.join(OUT, "xe_*.npz"))):
        seg = os.path.basename(f)[3:-4]
        if only and only not in seg:
            continue
        d = np.load(f)
        A, B = d["A"].astype(np.float32), d["B"].astype(np.float32)
        m, ca, cb = d["m"], d["ca"], d["cb"]

        called = ndimage.binary_dilation(ca | cb,
                                         iterations=1,
                                         structure=np.ones((3, 3)))
        called = ndimage.uniform_filter(called.astype(np.float32),
                                        2 * KEEPOUT_PX + 1) > 1e-6
        search = m & ~called & interior(m)
        frac = float(search.sum() / max(1, m.sum()))
        if search.sum() < 50000:
            print(f"{seg}  search area too small ({search.sum()} px), skipped")
            continue

        za, zb = zmap(A, m, search), zmap(B, m, search)
        if za is None or zb is None:
            print(f"{seg}  degenerate, skipped")
            continue
        J = np.minimum(za, zb)

        obs = peaks(J, search, TOPK, int(2 * LETTER_PX))
        obs_top = obs[0][0] if obs else 0.0

        # Spatial null: roll ONE scan's z-map. Preserves each map's histogram
        # and autocorrelation, destroys their mutual registration.
        lo = int(3 * LETTER_PX)
        null_top = []
        for _ in range(NULL_N):
            sy = int(rng.integers(lo, max(lo + 1, m.shape[0] - lo)))
            sx = int(rng.integers(lo, max(lo + 1, m.shape[1] - lo)))
            Jn = np.minimum(za, np.roll(zb, (sy, sx), (0, 1)))
            pk = peaks(Jn, search, 1, int(2 * LETTER_PX))
            null_top.append(pk[0][0] if pk else -np.inf)
        null_top = np.array(null_top, dtype=np.float64)
        p = float((null_top >= obs_top).sum() + 1) / (NULL_N + 1)

        surv = [dict(z=round(s, 2), y=y, x=x,
                     mm_y=round(y * DS8_UM / 1000, 1),
                     mm_x=round(x * DS8_UM / 1000, 1))
                for s, y, x in obs if s > np.percentile(null_top, 95)]

        np.savez_compressed(os.path.join(OUT, f"cj_{seg}.npz"),
                            J=J.astype(np.float16), search=search)
        report[seg] = dict(
            search_frac_of_shared=round(frac, 3),
            search_mm2=round(float(search.sum()) * (DS8_UM / 1000) ** 2, 1),
            keepout_mm=KEEPOUT_MM, edge_keepout_letters=1.5,
            min_box_cover=MIN_BOX_COVER, letter_px=round(LETTER_PX, 1),
            obs_top_z=round(obs_top, 2),
            null_top_mean=round(float(null_top.mean()), 2),
            null_top_p95=round(float(np.percentile(null_top, 95)), 2),
            p=round(p, 4), n_survivors=len(surv), survivors=surv)
        print(f"{seg}  search {100*frac:4.1f}% of shared ({report[seg]['search_mm2']:.0f} mm2)  "
              f"top z {obs_top:5.2f}  null {null_top.mean():5.2f} "
              f"(p95 {np.percentile(null_top,95):5.2f})  p={p:.3f}  "
              f"survivors {len(surv)}")

    # MERGE, never overwrite. Re-running one segment with a deeper null must
    # not wipe the other 36 — it did, once.
    path = os.path.join(OUT, "conjunction.json")
    prev = {}
    if os.path.exists(path):
        try:
            prev = json.load(open(path)).get("segments", {})
        except Exception:
            prev = {}
    for k, v in report.items():
        v["null_n"] = NULL_N
        prev[k] = v
    with open(path, "w") as f:
        json.dump(dict(um_per_px=DS8_UM, letter_mm=LETTER_MM, box_px=BOX,
                       keepout_mm=KEEPOUT_MM, null_n=NULL_N,
                       segments=prev), f, indent=1)
    print(f"\nwrote {OUT}/conjunction.json")


if __name__ == "__main__":
    main()
