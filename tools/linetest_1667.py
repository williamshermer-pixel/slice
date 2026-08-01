#!/usr/bin/env python3
"""Line test on the cross-energy conjunction map — look for a text LINE, not a
hot pixel.

Why this exists. The conjunction search takes the maximum of min(z59, z78) over
the whole uncalled sheet, and a maximum over millions of letter-boxes has a
high null: 4-7 sigma on 1667, purely from extreme-value statistics. A single
faint letter can never clear that bar, so the test as built can only find
something implausibly strong.

But ink is not distributed like noise. It comes in LINES — a run of letters at
a fixed pitch along a row. Integrating a run of eight letter-boxes along a line
aggregates eight boxes of evidence into one number, and noise does not line up.
That is a far better matched filter for text than a point maximum, and it costs
nothing extra: it runs on the J maps the conjunction search already wrote.

The filter is an anisotropic box — RUN_LETTERS long, 0.7 letter tall — swept at
several small angles, because flattened text lines are close to horizontal but
not exactly (the sheet undulates). Null is the same one the conjunction uses:
roll one scan's z-map, destroying mutual registration while preserving each
map's histogram and autocorrelation.

Still cannot rule out sheet condition, which also runs in bands along the
fibre direction. That is precisely why the angle sweep is reported: a survivor
whose best angle matches the fibre grain rather than the text baseline is
suspect, and the render decides.

    SCROLL=PHerc0139 python3 tools/linetest_1667.py [segment]
"""
import os, sys, glob, json
import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc1667")
if SCROLL not in HANDS:
    raise SystemExit(f"no cross-energy pair / measured hand for {SCROLL}")
_DIRS = {"PHerc1667": "s1667"}
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))

DS8_UM = 18.064
LETTER_MM = HANDS[SCROLL]
LETTER_PX = LETTER_MM * 1000.0 / DS8_UM
RUN_LETTERS = 8                       # a short word / line fragment
ANGLES = (-4.0, -2.0, 0.0, 2.0, 4.0)  # degrees off horizontal
NULL_N = int(os.environ.get('NULL_N', 199))


def line_kernel(angle):
    L = int(round(RUN_LETTERS * LETTER_PX))
    T = max(3, int(round(0.7 * LETTER_PX)))
    k = np.zeros((T, L), np.float32)
    k[:] = 1.0
    if abs(angle) > 1e-6:
        k = ndimage.rotate(k, angle, order=1, reshape=True)
        k[k < 0.5] = 0.0
    s = k.sum()
    return k / s if s > 0 else k


def line_score(J, search):
    """Best line response over the angle sweep. J is masked to the search area
    so called text and off-sheet contribute nothing."""
    x = np.where(search, J, 0.0).astype(np.float32)
    w = search.astype(np.float32)
    best = None
    best_ang = 0.0
    for a in ANGLES:
        k = line_kernel(a)
        num = fftconvolve(x, k, mode="same")
        den = fftconvolve(w, k, mode="same")
        r = np.where(den > 0.8, num / np.maximum(den, 1e-6), -np.inf)
        r = np.where(search, r, -np.inf)
        v = float(np.max(r)) if np.isfinite(r).any() else -np.inf
        if best is None or v > best:
            best, best_ang, bestmap = v, a, r
    return best, best_ang, bestmap


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    rng = np.random.default_rng(11)
    report = {}

    for f in sorted(glob.glob(os.path.join(OUT, "cj_*.npz"))):
        seg = os.path.basename(f)[3:-4]
        if only and only not in seg:
            continue
        d = np.load(f)
        if "za" not in d:
            print(f"{seg}  no za/zb in cj file — rerun conjunction first")
            continue
        za = d["za"].astype(np.float32)
        zb = d["zb"].astype(np.float32)
        search = d["search"]
        if search.sum() < 50000:
            continue

        obs, ang, rmap = line_score(np.minimum(za, zb), search)

        # THE NULL THAT WAS THE IDENTITY OPERATION. Rolling J and search
        # TOGETHER is exactly translation-equivariant for this score, so the
        # null returned the observation to the last decimal (measured: obs
        # 0.1008761, nulls 0.100876) and the test had ZERO power -- planting
        # real ink made it LESS significant. Roll only zb, as the conjunction
        # does, and rebuild the statistic; za stays put so the two maps are
        # genuinely de-registered.
        lo = int(3 * LETTER_PX)
        nulls = []
        for _ in range(NULL_N):
            sy = int(rng.integers(lo, max(lo + 1, za.shape[0] - lo)))
            sx = int(rng.integers(lo, max(lo + 1, za.shape[1] - lo)))
            zbr = np.roll(zb, (sy, sx), (0, 1))
            sr = np.roll(search, (sy, sx), (0, 1))
            reg = search & sr
            if reg.sum() < 1000:
                continue
            v, _, _ = line_score(np.minimum(za, zbr), reg)
            nulls.append(v)
        nulls = np.array([v for v in nulls if np.isfinite(v)])
        if nulls.size == 0:
            continue
        p = float((nulls >= obs).sum() + 1) / (nulls.size + 1)

        y, x = np.unravel_index(np.argmax(np.where(np.isfinite(rmap), rmap,
                                                   -np.inf)), rmap.shape)
        report[seg] = dict(
            run_letters=RUN_LETTERS, best_angle_deg=ang,
            obs_line_z=round(obs, 3),
            null_mean=round(float(nulls.mean()), 3),
            null_p95=round(float(np.percentile(nulls, 95)), 3),
            p=round(p, 4), y=int(y), x=int(x),
            mm_y=round(int(y) * DS8_UM / 1000, 1),
            mm_x=round(int(x) * DS8_UM / 1000, 1))
        flag = "  <-- SURVIVOR" if p <= 0.05 else ""
        print(f"{seg}  line z {obs:6.3f} @ {ang:+.0f}deg  "
              f"null {nulls.mean():6.3f} (p95 {np.percentile(nulls,95):6.3f})  "
              f"p={p:.3f}{flag}")

    with open(os.path.join(OUT, "linetest.json"), "w") as f:
        json.dump(dict(scroll=SCROLL, letter_mm=LETTER_MM,
                       run_letters=RUN_LETTERS, angles=list(ANGLES),
                       null_n=NULL_N, segments=report), f, indent=1)
    print(f"\nwrote {OUT}/linetest.json")


if __name__ == "__main__":
    main()
