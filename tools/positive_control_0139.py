"""POSITIVE CONTROL — would this pipeline see a letter if one were there?

The calibrated differential reports SILENCE across 57 windows of the lost
book. That is only a finding if the same gates, at the same floor, can
recover letters that are KNOWN to exist. Otherwise the silence just measures
how blind the instrument is.

Method: use the published map's own isolated, letter-sized components as
ground-truth letter locations (his measured hand: 0.7-2.2 mm). For each,
ask whether our map -- thresholded at the SAME absolute floor -- puts a
stroke-like component on it. That fraction is the pipeline's detection rate
on real letters of this scribe, and it is the number that makes the margin
silence interpretable.

  python3 tools/positive_control_0139.py
"""
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D

MAX_WINDOWS = 12


def isolated_letters(pub):
    """Letter-sized components of the PUBLISHED map = known letters."""
    out = []
    for c in D.components(pub > 128):
        span = max(c["y1"] - c["y0"], c["x1"] - c["x0"])
        if c["area"] >= 200 and D.LETTER_LO <= span <= D.LETTER_HI:
            out.append(c)
    return out


def main():
    floor = D.floor_value()
    print(f"floor {floor:.4f} (calibrated at 0.2% blank FPR)\n")
    print(f"{'segment':28} {'known':>6} {'hit':>5} {'rate':>7} {'shape-ok':>9}")
    tot_known = tot_hit = tot_shape = 0
    rows = []
    maps = sorted(glob.glob(os.path.join(D.LB, "map_s*.npy")))
    used = 0
    for mp in maps:
        if used >= MAX_WINDOWS:
            break
        tag = os.path.basename(mp)[4:-4]
        meta = json.load(open(os.path.join(D.LB, f"meta_{tag}.json")))
        if meta["aim"] < 0.25:
            continue
        try:
            pub = D.pub_crop(meta)
        except Exception:
            continue
        known = isolated_letters(pub)
        if len(known) < 5:
            continue
        used += 1
        ours = np.load(mp)
        hot = D.hot_mask(ours, floor)
        ourcomps = D.components(hot)
        hit = shape_ok = 0
        for k in known:
            # does any of our components overlap this known letter's box?
            best = None
            for c in ourcomps:
                if (c["x0"] <= k["x1"] and c["x1"] >= k["x0"]
                        and c["y0"] <= k["y1"] and c["y1"] >= k["y0"]):
                    if best is None or c["area"] > best["area"]:
                        best = c
            if best is not None:
                hit += 1
                span = max(best["y1"] - best["y0"], best["x1"] - best["x0"])
                if (D.LETTER_LO <= span <= D.LETTER_HI
                        and D.is_strokelike(best)):
                    shape_ok += 1
        rate = hit / len(known)
        print(f"{meta['seg'].split('/')[-2][:28]:28} {len(known):6d} {hit:5d} "
              f"{100*rate:6.1f}% {shape_ok:9d}")
        tot_known += len(known); tot_hit += hit; tot_shape += shape_ok
        rows.append(dict(seg=meta["seg"], tag=tag, known=len(known),
                         hit=hit, shape_ok=shape_ok, rate=round(rate, 3)))

    if not tot_known:
        sys.exit("no usable text windows")
    det = tot_hit / tot_known
    shp = tot_shape / tot_known
    print(f"\nOVER {used} WINDOWS: {tot_known} known letters, "
          f"{tot_hit} touched by our confident mask ({100*det:.1f}%), "
          f"{tot_shape} also passing the SHAPE gate ({100*shp:.1f}%)")
    json.dump(dict(floor=floor, windows=used, known=tot_known, hit=tot_hit,
                   shape_ok=tot_shape, detection_rate=round(det, 4),
                   shape_pass_rate=round(shp, 4), per_window=rows),
              open(os.path.join(D.LB, "positive_control.json"), "w"), indent=1)

    # STATISTICAL POWER: the differential requires >=2 stroke-like comps in a
    # window. With per-letter shape-pass probability shp, a hidden margin line
    # of N letters is detected with P(>=2 of N). This is the number that says
    # whether silence means anything.
    print(f"\nPOWER of the >=2-component gate at p={shp:.3f} per letter:")
    print(f"{'hidden letters':>15} {'P(detect)':>10}")
    powers = {}
    for N in (3, 5, 10, 20, 40):
        p0 = (1 - shp) ** N
        p1 = N * shp * (1 - shp) ** (N - 1)
        pw = 1 - p0 - p1
        powers[N] = round(float(pw), 4)
        print(f"{N:15d} {100*pw:9.1f}%")

    print()
    if shp < 0.05:
        print("VERDICT: the SHAPE gate does not recognise this scribe's own\n"
              "known letters. The margin silence is UNINTERPRETABLE — it\n"
              "measures the gate's blindness, not the papyrus.")
    elif powers[10] < 0.5:
        print("VERDICT: UNDERPOWERED, and this is the headline. Our maps DO\n"
              f"respond at {100*det:.0f}% of his known letters, but only "
              f"{100*shp:.0f}% survive\n"
              "the shape gate — so a hidden margin line of ten letters would be\n"
              f"caught only {100*powers[10]:.0f}% of the time. The 57-window "
              "silence is therefore\n"
              "NOT evidence of absence. It is a measurement of the resolution\n"
              "ceiling: at his 1.61 mm hand the model responds to letters but\n"
              "does not resolve their stroke structure. Report as a ceiling\n"
              "finding, never as 'the margins are empty'.")
    else:
        print("VERDICT: the pipeline demonstrably finds this scribe's known\n"
              "letters with adequate power, so margin silence is a real,\n"
              "calibrated negative.")
    json.dump(dict(floor=floor, windows=used, known=tot_known, hit=tot_hit,
                   shape_ok=tot_shape, detection_rate=round(det, 4),
                   shape_pass_rate=round(shp, 4), power=powers,
                   per_window=rows),
              open(os.path.join(D.LB, "positive_control.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
