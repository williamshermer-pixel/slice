"""CONDITION CONTROL for the letter-scale detector.

This project's most expensive lesson: every high scorer it ever found was
detecting PAPYRUS CONDITION, not ink, because text sits on well-preserved
sheet. "offaxis+hfenergy" scored r=+0.444 held-out and 0.209 on blank.

The letter-scale detector scores AUC 0.983 separating known letters from
blank boxes -- but those blank boxes were drawn wherever the published map is
uncalled, which is mostly inter-column space and margins: DIFFERENT SHEET
REGIONS, different condition. That AUC may be region contrast.

This control redraws the null from blank boxes INSIDE the text block -- the
gaps between letters and between lines, same local sheet, same condition,
same distance from damage. If the AUC survives, the detector separates ink
from not-ink. If it collapses, it separates text regions from non-text
regions and must not be used to hunt.

  python3 tools/condition_control_0139.py
"""
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D
import positive_control_0139 as P
from letterscale_0139 import boxmean, BOX


def auc_of(a, b):
    s = np.concatenate([a, b])
    y = np.concatenate([np.ones(a.size, bool), np.zeros(b.size, bool)])
    idx = np.argsort(s)
    rk = np.empty(s.size); rk[idx] = np.arange(1, s.size + 1)
    n1, n0 = int(y.sum()), int((~y).sum())
    v = (rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    return float(max(v, 1 - v))


def main():
    ink, near, far = [], [], []
    windows = 0
    rng = np.random.default_rng(5)
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
        called = (pub > 128).astype(np.float32)
        blankfrac = boxmean(1.0 - called, BOX)
        blank_ok = blankfrac > 0.999

        # "near" = blank box whose neighbourhood IS text: dilate called by one
        # line pitch and require the blank box to sit inside that halo.
        k = int(D.PITCH)
        halo = boxmean(called, min(k, min(bm.shape) - 1))
        hp = np.zeros_like(blank_ok)
        n0 = min(halo.shape[0], blank_ok.shape[0])
        n1 = min(halo.shape[1], blank_ok.shape[1])
        hp[:n0, :n1] = halo[:n0, :n1] > 0.02        # >=2% text within a pitch
        nearmask = blank_ok & hp
        farmask = blank_ok & ~hp

        for name, m, acc in (("near", nearmask, near), ("far", farmask, far)):
            v = bm[m]
            if v.size:
                if v.size > 8000:
                    v = rng.choice(v, 8000, replace=False)
                acc.append(v)
        for kk in known:
            cy = max(0, min(bm.shape[0]-1, int(round(kk["cy"])) - BOX//2))
            cx = max(0, min(bm.shape[1]-1, int(round(kk["cx"])) - BOX//2))
            ink.append(bm[cy, cx])
        if windows >= 12:
            break

    ink = np.array(ink, np.float32)
    near = np.concatenate(near) if near else np.array([], np.float32)
    far = np.concatenate(far) if far else np.array([], np.float32)
    print(f"{windows} windows | {ink.size} known letters | "
          f"{near.size} blank-boxes INSIDE text | {far.size} blank-boxes AWAY\n")
    if near.size < 500:
        sys.exit("not enough in-text blank area to control — inconclusive")

    a_far = auc_of(ink, far) if far.size else float("nan")
    a_near = auc_of(ink, near)
    print(f"AUC letters vs blank AWAY from text (uncontrolled) : {a_far:.3f}")
    print(f"AUC letters vs blank INSIDE text  (controlled)     : {a_near:.3f}")
    print(f"median box-mean  letters {np.median(ink):.4f} | "
          f"in-text blank {np.median(near):.4f} | away {np.median(far):.4f}"
          if far.size else "")

    thr = float(np.percentile(near, 99.9))
    det = float((ink > thr).mean())
    print(f"\nthreshold at 0.1% FPR on IN-TEXT blank : {thr:.4f}")
    print(f"detection rate on known letters        : {100*det:.1f}%")
    powers = {}
    for N in (3, 5, 10, 20):
        p0 = (1-det)**N; p1 = N*det*(1-det)**(N-1)
        powers[N] = round(float(1-p0-p1), 4)
    print("power >=2 of N: " + "  ".join(f"N={n}:{100*v:.0f}%"
                                        for n, v in powers.items()))
    json.dump(dict(auc_far=round(a_far, 4), auc_near=round(a_near, 4),
                   threshold_near=thr, detection_rate=round(det, 4),
                   power=powers, n_known=int(ink.size),
                   n_near=int(near.size), n_far=int(far.size)),
              open(os.path.join(D.LB, "condition_control.json"), "w"), indent=1)
    print()
    drop = (a_far - a_near) if far.size else 0.0
    if a_near < 0.70:
        print("VERDICT: the detector was reading REGION/CONDITION contrast.\n"
              "Controlled against same-condition blank sheet it cannot tell a\n"
              "letter from the gap beside it. Do NOT hunt with it.")
    elif drop > 0.15:
        print(f"VERDICT: real but inflated — AUC drops {drop:.3f} when the null\n"
              "is same-condition sheet. The controlled number is the honest one;\n"
              "hunt with the in-text threshold only.")
    else:
        print("VERDICT: survives the condition control. The detector separates\n"
              "ink from adjacent blank sheet of the SAME condition, which is\n"
              "the discrimination this project has never had. Hunt with it.")


if __name__ == "__main__":
    main()
