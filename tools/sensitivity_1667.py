#!/usr/bin/env python3
"""How faint a letter would the conjunction search have caught?

A negative result is only worth reading if its sensitivity is a number. "We
searched 245 cm2 and found nothing" is uninformative on its own — nothing is
exactly what you get from a blind instrument. This measures the detection
limit by injection recovery, the same way the rest of this project turns
silences into statements (the differential hunt quotes 78-98% per letter).

Method. Take a segment's two registered maps. Measure the amplitude of REAL
called ink in the letter-box high-passed representation — that is the natural
unit, so alpha = 1.0 means "as strong as a typical published call on this very
sheet". Then plant K well-separated synthetic letters of amplitude alpha into
BOTH scans at the same place (real ink appears in both; that is the entire
premise of the conjunction), inside the search region only, re-run the exact
detection path, and count how many are recovered as peaks clearing the
uninjected run's null threshold.

Power at each alpha is recovered/K. The reported detection limit is the
smallest alpha reaching 90% power.

Two honesties about what this does and does not model:

  - Injected letters are Gaussian blobs at the measured hand, not letterforms.
    At 1.6 mm the model's own response to real ink is a letter-sized mass
    rather than a resolved glyph (256 px tile = 578 um field of view), so a
    blob is a fair stand-in for what the maps actually contain. It would NOT
    be fair at Scroll 1's 3.00 mm hand.
  - Injecting into both scans at identical amplitude is the BEST case. Real
    ink need not present equally at 59 and 78 keV, so the true limit is
    somewhat worse than what this reports. Stated, not hidden.

    SCROLL=PHerc0139 python3 tools/sensitivity_1667.py [segment]
"""
import glob, json, os, sys
import numpy as np
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc0139")
_DIRS = {"PHerc1667": "s1667"}
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))

DS8_UM = 18.064
LETTER_MM = HANDS[SCROLL]
LETTER_PX = LETTER_MM * 1000.0 / DS8_UM
BOX = max(3, int(round(0.7 * LETTER_PX)))
MIN_BOX_COVER = 0.95
KEEPOUT_PX = int(round(1.5 * 1000.0 / DS8_UM))
ALPHAS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
K = 12                                  # injected letters per trial
TRIALS = int(os.environ.get("TRIALS", 3))
NULL_N = int(os.environ.get("NULL_N", 60))


def letter_box(a, m):
    a = np.where(m, a, 0.0)
    num = ndimage.uniform_filter(a, BOX)
    den = ndimage.uniform_filter(m.astype(np.float32), BOX)
    return np.where(den >= MIN_BOX_COVER, num / np.maximum(den, 1e-6), 0.0)


def zmap(a, m, search):
    hp = a - ndimage.gaussian_filter(np.where(m, a, 0.0), LETTER_PX)
    L = letter_box(hp, m)
    v = L[search]
    if v.size < 100 or v.std() < 1e-9:
        return None
    return (L - v.mean()) / v.std()


def peaks(J, search, k, sep):
    out, work = [], np.where(search, J, -np.inf)
    for _ in range(k):
        i = np.unravel_index(np.argmax(work), work.shape)
        if not np.isfinite(work[i]):
            break
        out.append((float(work[i]), int(i[0]), int(i[1])))
        work[max(0, i[0]-sep):i[0]+sep, max(0, i[1]-sep):i[1]+sep] = -np.inf
    return out


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    rng = np.random.default_rng(23)
    report = {}

    for f in sorted(glob.glob(os.path.join(OUT, "xe_*.npz"))):
        seg = os.path.basename(f)[3:-4]
        if only and only not in seg:
            continue
        d = np.load(f)
        A, B = d["A"].astype(np.float32), d["B"].astype(np.float32)
        m, ca, cb = d["m"], d["ca"], d["cb"]

        called = ndimage.uniform_filter((ca | cb).astype(np.float32),
                                        2 * KEEPOUT_PX + 1) > 1e-6
        dist = ndimage.distance_transform_edt(m)
        search = m & ~called & (dist >= 1.5 * LETTER_PX)
        if search.sum() < 50000:
            continue

        # amplitude of real called ink, in the same representation the search
        # uses -- this is what alpha = 1.0 means
        hpA = A - ndimage.gaussian_filter(np.where(m, A, 0.0), LETTER_PX)
        LA = letter_box(hpA, m)
        ink_amp = float(np.median(LA[ca & m])) if (ca & m).any() else 0.0
        if ink_amp <= 0:
            continue

        za, zb = zmap(A, m, search), zmap(B, m, search)
        if za is None or zb is None:
            continue
        J = np.minimum(za, zb)

        # threshold the real search had to beat
        lo = int(3 * LETTER_PX)
        nulls = []
        for _ in range(NULL_N):
            sy = int(rng.integers(lo, max(lo + 1, m.shape[0] - lo)))
            sx = int(rng.integers(lo, max(lo + 1, m.shape[1] - lo)))
            pk = peaks(np.minimum(za, np.roll(zb, (sy, sx), (0, 1))),
                       search, 1, int(2 * LETTER_PX))
            nulls.append(pk[0][0] if pk else -np.inf)
        thr = float(np.percentile([v for v in nulls if np.isfinite(v)], 95))

        # How much of the search region can actually HOST a letter? The
        # uncalled sheet is narrow ribbons between text, not open field, so
        # area alone overstates coverage badly: on PHerc0139 20260317000000 the
        # largest inscribed circle in the search region is 1.20 letters and
        # only 0.79% of it has a full letter of clearance. Injection sites must
        # respect that, and the effective area is reported alongside the raw.
        clear = ndimage.distance_transform_edt(search)
        eff = clear >= LETTER_PX
        host = clear >= 0.75 * LETTER_PX          # minimum to plant a letter
        ys, xs = np.where(host)
        if ys.size == 0:
            report[seg] = dict(
                search_mm2=round(float(search.sum()) * (DS8_UM/1000)**2, 1),
                effective_mm2=0.0, max_clearance_letters=round(
                    float(clear.max()) / LETTER_PX, 2),
                power_by_alpha={}, detection_limit_alpha_at_90pct_power=None,
                note="no site in the search region can host a letter")
            print(f"{seg}  NO HOSTABLE SITE (max clearance "
                  f"{clear.max()/LETTER_PX:.2f} letters)")
            continue
        sigma = LETTER_PX / 2.355            # FWHM = one letter
        yy = np.arange(-int(1.2*LETTER_PX), int(1.2*LETTER_PX) + 1)
        g = np.exp(-(yy**2) / (2 * sigma**2))
        stamp = np.outer(g, g).astype(np.float32)

        powers = {}
        for alpha in ALPHAS:
            hits = tot = 0
            for _ in range(TRIALS):
                Ai, Bi = A.copy(), B.copy()
                pts, guard = [], np.zeros_like(search)
                for _ in range(K * 8):
                    if len(pts) >= K:
                        break
                    i = int(rng.integers(0, ys.size))
                    y, x = int(ys[i]), int(xs[i])
                    if guard[y, x]:
                        continue
                    h = stamp.shape[0] // 2
                    if not (h < y < A.shape[0]-h and h < x < A.shape[1]-h):
                        continue
                    sl = (slice(y-h, y+h+1), slice(x-h, x+h+1))
                    if search[sl].mean() < 0.6:
                        continue
                    Ai[sl] += alpha * ink_amp * stamp
                    Bi[sl] += alpha * ink_amp * stamp
                    pts.append((y, x))
                    guard[max(0,y-4*int(LETTER_PX)):y+4*int(LETTER_PX),
                          max(0,x-4*int(LETTER_PX)):x+4*int(LETTER_PX)] = True
                if not pts:
                    continue
                zai, zbi = zmap(Ai, m, search), zmap(Bi, m, search)
                if zai is None or zbi is None:
                    continue
                Ji = np.minimum(zai, zbi)
                found = peaks(Ji, search, len(pts) * 3, int(2 * LETTER_PX))
                found = [(v, y, x) for v, y, x in found if v > thr]
                for (py, px) in pts:
                    tot += 1
                    if any((py-y)**2 + (px-x)**2 <= (1.5*LETTER_PX)**2
                           for _, y, x in found):
                        hits += 1
            powers[alpha] = round(hits / tot, 3) if tot else None

        lim = next((a for a in ALPHAS
                    if powers.get(a) is not None and powers[a] >= 0.9), None)
        report[seg] = dict(ink_amplitude_unit=round(ink_amp, 5),
                           null_p95_threshold=round(thr, 2),
                           power_by_alpha=powers,
                           detection_limit_alpha_at_90pct_power=lim,
                           search_mm2=round(float(search.sum()) *
                                            (DS8_UM/1000)**2, 1),
                           effective_mm2=round(float(eff.sum()) *
                                               (DS8_UM/1000)**2, 1),
                           hostable_mm2=round(float(host.sum()) *
                                              (DS8_UM/1000)**2, 1),
                           max_clearance_letters=round(
                               float(clear.max()) / LETTER_PX, 2))
        print(f"{seg}  " + "  ".join(f"a{a}:{powers[a]}" for a in ALPHAS) +
              f"   limit(90%) {lim}")

    p = os.path.join(OUT, "sensitivity.json")
    json.dump(dict(scroll=SCROLL, letter_mm=LETTER_MM, alphas=list(ALPHAS),
                   injected_per_trial=K, trials=TRIALS,
                   note="alpha = 1.0 is the median letter-box amplitude of REAL "
                        "published ink calls on the same segment. Injecting "
                        "equally into both scans is the BEST case; real ink need "
                        "not present equally at 59 and 78 keV, so the true limit "
                        "is somewhat worse.",
                   segments=report), open(p, "w"), indent=1)
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
