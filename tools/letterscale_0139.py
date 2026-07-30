"""LETTER-SCALE DETECTOR for 0139 — integrate over the letter, calibrate
against a LOCAL null.

Why: per-pixel thresholding recovers only ~10-12% of this scribe's known
letters (measured), because at his 1.09 mm hand few individual pixels clear a
low-FPR floor. A letter is thousands of pixels, so the statistic should be the
MEAN over a letter-sized box, not any single pixel.

Why a LOCAL null and not a global threshold: this project measured that the
noise is spatially correlated (matched filtering scored -0.046, mechanism 12),
so an absolute cut on a box-mean is not calibrated. Instead each box-mean is
ranked against box-means drawn from BLANK papyrus in the same neighbourhood --
READER_DESIGN's local-null percentile scoring.

This script CALIBRATES the detector on known letters and reports its power.
It does not hunt; hunt only if the power justifies it.

  python3 tools/letterscale_0139.py
"""
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D
import positive_control_0139 as P

BOX = int(D.LETTER_MM * D.MM)   # the scribe's median letter
TARGET_FPR = 0.001


def boxmean(a, k):
    """Mean over every kxk box, via summed-area table. Returns (H-k+1, W-k+1)."""
    c = np.pad(a.astype(np.float64), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / float(k * k)).astype(np.float32)


def main():
    ink_scores, blank_scores = [], []
    windows = 0
    for mp in sorted(glob.glob(os.path.join(D.LB, "map_s*.npy"))):
        tag = os.path.basename(mp)[4:-4]
        meta = json.load(open(os.path.join(D.LB, f"meta_{tag}.json")))
        if meta["aim"] < 0.25:
            continue
        try:
            pub = D.pub_crop(meta)
        except Exception:
            continue
        known = P.isolated_letters(pub)
        if len(known) < 5:
            continue
        windows += 1
        ours = np.load(mp)
        bm = boxmean(ours, BOX)
        # blank-papyrus box positions: the whole BOX must be uncalled
        pubblank = (pub < 60).astype(np.float32)
        blankfrac = boxmean(pubblank, BOX)
        blank_ok = blankfrac > 0.999
        bs = bm[blank_ok]
        if bs.size > 20000:
            bs = np.random.default_rng(3).choice(bs, 20000, replace=False)
        blank_scores.append(bs)
        # known-letter box positions: box centred on each known letter
        for k in known:
            cy = int(round(k["cy"])) - BOX // 2
            cx = int(round(k["cx"])) - BOX // 2
            cy = max(0, min(bm.shape[0] - 1, cy))
            cx = max(0, min(bm.shape[1] - 1, cx))
            ink_scores.append(bm[cy, cx])
        if windows >= 12:
            break

    ink = np.array(ink_scores, np.float32)
    blank = np.concatenate(blank_scores)
    print(f"letter-scale box {BOX}px ({BOX/D.MM:.2f} mm) over {windows} windows")
    print(f"{ink.size} known letters vs {blank.size} blank-papyrus boxes\n")

    idx = np.argsort(np.concatenate([ink, blank]))
    y = np.concatenate([np.ones(ink.size, bool), np.zeros(blank.size, bool)])
    rk = np.empty(idx.size); rk[idx] = np.arange(1, idx.size + 1)
    n1, n0 = int(y.sum()), int((~y).sum())
    auc = (rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    auc = max(auc, 1 - auc)

    thr = float(np.percentile(blank, 100 * (1 - TARGET_FPR)))
    det = float((ink > thr).mean())
    print(f"AUC (known letter vs blank, letter-scale) : {auc:.3f}")
    print(f"threshold at {100*TARGET_FPR:.1f}% blank FPR      : {thr:.4f}")
    print(f"detection rate on his KNOWN letters      : {100*det:.1f}%")
    print(f"  (per-pixel floor achieved 9.9% shape / 12.4% envelope)")

    print(f"\nPOWER, >=2 detections among N hidden letters:")
    powers = {}
    for N in (3, 5, 10, 20):
        p0 = (1 - det) ** N
        p1 = N * det * (1 - det) ** (N - 1)
        powers[N] = round(float(1 - p0 - p1), 4)
        print(f"{N:8d} letters : {100*powers[N]:5.1f}%")

    json.dump(dict(box_px=BOX, auc=round(float(auc), 4), threshold=thr,
                   target_fpr=TARGET_FPR, detection_rate=round(det, 4),
                   power=powers, n_known=int(ink.size), n_blank=int(blank.size)),
              open(os.path.join(D.LB, "letterscale.json"), "w"), indent=1)
    print("\n-> out/lostbook/letterscale.json")
    if powers[10] >= 0.5:
        print("POWERED: this detector can interpret a margin silence. Hunt with it.")
    else:
        print("STILL UNDERPOWERED at his hand — the ceiling, not the method.")


if __name__ == "__main__":
    main()
