"""CALIBRATE the differential's absolute confidence floor on ground truth.

The spatial null killed every relative-threshold candidate (top-4% of a map
selects 4% of pixels whether ink exists or not). The fix is an ABSOLUTE floor:
what probability does this model actually assign to THIS scribe's known ink?

Measured on the text-band windows, where the published map is ground truth:
  - distribution of our probability at published-INK pixels
  - distribution at published-BLANK pixels
The floor is the level below which the model does not reliably mark his ink.
Everything the differential reports must clear it, or it is not "our map is
confident" — it is only "our map is relatively hottest here".

  python3 tools/calibrate_floor.py
"""
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D


def main():
    rows = []
    for mp in sorted(glob.glob(os.path.join(D.LB, "map_s*.npy"))):
        tag = os.path.basename(mp)[4:-4]
        meta = json.load(open(os.path.join(D.LB, f"meta_{tag}.json")))
        if meta["aim"] < 0.25:            # calibrate on TEXT, not margins
            continue
        try:
            pub = D.pub_crop(meta)
        except Exception as e:
            print(f"{tag}: pub fetch failed {e}")
            continue
        ours = np.load(mp)
        ink = pub > 128
        blank = pub < 60
        if ink.sum() < 5000 or blank.sum() < 5000:
            continue
        rows.append((ours[ink], ours[blank], meta["seg"]))

    if not rows:
        sys.exit("no text-band windows available")
    ink_all = np.concatenate([r[0] for r in rows])
    blank_all = np.concatenate([r[1] for r in rows])
    print(f"calibrating on {len(rows)} text-band windows "
          f"({ink_all.size/1e6:.1f}M ink px, {blank_all.size/1e6:.1f}M blank px)\n")

    qs = [5, 10, 25, 50, 75, 90]
    print(f"{'quantile':>9} {'at KNOWN ink':>13} {'at blank':>10}")
    for q in qs:
        print(f"{q:8d}% {np.percentile(ink_all, q):13.4f} "
              f"{np.percentile(blank_all, q):10.4f}")

    # AUC of our maps against published calls — is the instrument working here?
    s = np.concatenate([ink_all, blank_all])
    y = np.concatenate([np.ones(ink_all.size, bool), np.zeros(blank_all.size, bool)])
    idx = np.argsort(s)
    rk = np.empty(s.size)
    rk[idx] = np.arange(1, s.size + 1)
    n1, n0 = int(y.sum()), int((~y).sum())
    auc = (rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    auc = max(auc, 1 - auc)

    print(f"\nour maps vs published calls on his text: AUC {auc:.3f}")

    # Choose the operating point by FALSE-POSITIVE RATE on known-blank papyrus.
    # A discovery search must almost never fire on blank sheet, or the margins
    # (which are mostly blank) fill with noise -- the exact failure the spatial
    # null just exposed.
    TARGET_FPR = 0.002
    floor = float(np.percentile(blank_all, 100 * (1 - TARGET_FPR)))
    sens = float((ink_all > floor).mean())
    blank_rate = float((blank_all > floor).mean())
    print(f"{'floor':>8} {'blank FPR':>10} {'ink sens':>9}")
    for f in [0.4073, 0.5, 0.6, 0.7, floor, 0.8, 0.9]:
        print(f"{f:8.4f} {100*(blank_all > f).mean():9.3f}% "
              f"{100*(ink_all > f).mean():8.2f}%")
    print(f"\nFLOOR = {floor:.4f}  (blank FPR {100*blank_rate:.3f}%, "
          f"catches {100*sens:.1f}% of his known ink pixels)")
    print("Rationale: at this level blank papyrus essentially never fires, so a\n"
          "letter-sized cluster clearing it is not the noisiest-4% artifact the\n"
          "spatial null killed. Sensitivity is the price and it is acceptable:\n"
          "a letter is thousands of pixels, so partial coverage still shows.")
    json.dump(dict(floor=floor, target_fpr=TARGET_FPR,
                   sensitivity=round(sens, 4), auc=round(float(auc), 4),
                   blank_fpr=round(blank_rate, 5),
                   n_windows=len(rows),
                   ink_q={str(q): round(float(np.percentile(ink_all, q)), 4)
                          for q in qs},
                   blank_q={str(q): round(float(np.percentile(blank_all, q)), 4)
                            for q in qs}),
              open(os.path.join(D.LB, "floor.json"), "w"), indent=1)
    print(f"\nwritten to out/lostbook/floor.json — differential reads it")


if __name__ == "__main__":
    main()
