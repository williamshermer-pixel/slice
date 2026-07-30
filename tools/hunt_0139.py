"""THE HUNT — letter-scale, condition-controlled, spillover-safe search for
ink in PHerc0139 that the published maps never called.

Design, each element forced by a measured failure:

  detector    mean probability over a letter-sized box (his 1.09 mm hand).
              Per-pixel thresholding recovered only 10-12% of his known
              letters; the box-mean scores AUC 0.967 against blank sheet of
              the SAME condition, so it reads ink, not preservation.

  null        blank boxes at least 2 letter-widths from ANY called pixel.
              Two contaminations forced this: the model's response smears
              past a letter's called extent (spillover), and blank sheet
              beside text may hold the uncalled ink we are hunting. The null
              must be geometry-matched to where candidates are allowed.

  candidates  boxes clearing the null's 99.9th percentile, at least 2 letter
              widths from called ink, clustered and rhythm-checked at his
              measured 0.70 mm advance.

  validation  every survivor gets a SPATIAL NULL (roll our own map, identical
              histogram and autocorrelation, registration destroyed). The
              relative-threshold version of this search produced 3 candidates
              and 23/24 rolls reproduced them; nothing ships without it.

  python3 tools/hunt_0139.py
"""
import glob, json, os, sys
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D
from letterscale_0139 import boxmean, BOX

CLEAR = 2 * BOX            # spillover keep-out from any called pixel
N_ROLL = 24
RNG = np.random.default_rng(23)


def masks_for(ours, pub):
    """box-mean map, plus which box positions are legal candidates/null."""
    bm = boxmean(ours, BOX)
    called = (pub > 128).astype(np.float32)
    # fraction of a CLEAR-sized box that is called; 0 => nothing called near
    k = min(CLEAR, min(called.shape) - 1)
    nearcalled = boxmean(called, k)
    pad = np.zeros(bm.shape, bool)
    n0 = min(nearcalled.shape[0], bm.shape[0])
    n1 = min(nearcalled.shape[1], bm.shape[1])
    pad[:n0, :n1] = nearcalled[:n0, :n1] <= 0.0
    # the box itself must be uncalled too
    blankfrac = boxmean(1.0 - called, BOX)
    ownblank = blankfrac > 0.999
    legal = pad & ownblank
    return bm, legal


def find(bm, legal, thr):
    """Letter-sized clusters of legal boxes above thr."""
    hot = legal & (bm > thr)
    if not hot.any():
        return [], 0.0, hot
    comps = [c for c in D.components(hot)
             if c["area"] >= 20]                   # box centres, not pixels
    comps = [c for c in comps
             if max(c["y1"]-c["y0"], c["x1"]-c["x0"]) <= 3 * D.LETTER_HI]
    return comps, D.rhythm(hot, comps), hot


def main():
    ls = json.load(open(os.path.join(D.LB, "letterscale.json")))
    print(f"box {BOX}px ({BOX/D.MM:.2f} mm) | keep-out {CLEAR}px from called ink")

    # ---- calibrate the geometry-matched null on TEXT windows -------------
    nullvals = []
    for mp in sorted(glob.glob(os.path.join(D.LB, "map_s*.npy"))):
        tag = os.path.basename(mp)[4:-4]
        meta = json.load(open(os.path.join(D.LB, f"meta_{tag}.json")))
        if meta["aim"] < 0.25:
            continue
        try:
            pub = D.pub_crop(meta)
        except Exception:
            continue
        bm, legal = masks_for(np.load(mp), pub)
        v = bm[legal]
        if v.size:
            nullvals.append(v if v.size < 20000 else
                            RNG.choice(v, 20000, replace=False))
        if len(nullvals) >= 14:
            break
    if not nullvals:
        sys.exit("no legal null area found")
    nv = np.concatenate(nullvals)
    thr = float(np.percentile(nv, 99.9))
    print(f"null: {nv.size} spillover-safe blank boxes | median {np.median(nv):.4f}"
          f" | p99.9 THRESHOLD {thr:.4f}")
    print(f"(letters median {0.4339:.4f} for reference; detector AUC "
          f"{ls['auc']:.3f} uncontrolled / 0.967 condition-controlled)\n")

    # ---- hunt every window ---------------------------------------------
    print(f"{'segment':28} {'aim':>5} {'legal%':>7} {'clusters':>9} {'rhythm':>7}")
    hits = []
    for mp in sorted(glob.glob(os.path.join(D.LB, "map_s*.npy"))):
        tag = os.path.basename(mp)[4:-4]
        meta = json.load(open(os.path.join(D.LB, f"meta_{tag}.json")))
        try:
            pub = D.pub_crop(meta)
        except Exception:
            continue
        ours = np.load(mp)
        bm, legal = masks_for(ours, pub)
        if legal.mean() < 0.01:
            continue
        comps, r, hot = find(bm, legal, thr)
        flag = ""
        if len(comps) >= 2:
            flag = "  <-- CANDIDATE"
            hits.append(dict(tag=tag, seg=meta["seg"], aim=meta["aim"],
                             window=meta["window"], n=len(comps),
                             rhythm=round(r, 3),
                             peak=round(float(bm[hot].max()), 4)))
        if len(comps) or legal.mean() > 0.2:
            print(f"{meta['seg'].split('/')[-2][:28]:28} {meta['aim']:5.2f} "
                  f"{100*legal.mean():6.1f}% {len(comps):9d} {r:7.3f}{flag}")

    print(f"\n{len(hits)} windows with >=2 clusters")
    if not hits:
        print("\nNo ink outside the published calls at this detector's\n"
              "sensitivity, across every window mapped. With ~77% per-letter\n"
              "detection against a distant null and a spillover-safe null used\n"
              "here, this is a CALIBRATED negative, not a blind one.")
        json.dump(dict(threshold=thr, candidates=[], n_null=int(nv.size)),
                  open(os.path.join(D.LB, "hunt.json"), "w"), indent=1)
        return

    # ---- mandatory spatial null on every survivor -----------------------
    print("\nspatial null on each candidate (roll our map, same stats):")
    survivors = []
    for h in hits:
        ours = np.load(os.path.join(D.LB, f"map_{h['tag']}.npy"))
        meta = json.load(open(os.path.join(D.LB, f"meta_{h['tag']}.json")))
        pub = D.pub_crop(meta)
        _, legal = masks_for(ours, pub)
        beat = 0
        for _ in range(N_ROLL):
            dy = int(RNG.integers(ours.shape[0]//8, ours.shape[0]-ours.shape[0]//8))
            dx = int(RNG.integers(ours.shape[1]//8, ours.shape[1]-ours.shape[1]//8))
            rl = np.roll(np.roll(ours, dy, 0), dx, 1)
            c2, _, _ = find(boxmean(rl, BOX), legal, thr)
            if len(c2) >= h["n"]:
                beat += 1
        p = (beat + 1) / (N_ROLL + 1)
        h["null_beat"] = beat
        h["p"] = round(p, 4)
        h["survives"] = bool(p < 0.05)
        print(f"  {h['seg'].split('/')[-2][:26]:26} n={h['n']} peak {h['peak']:.3f} "
              f"nulls>=n {beat}/{N_ROLL} p={p:.3f} "
              f"{'SURVIVES' if h['survives'] else 'dead'}")
        if h["survives"]:
            survivors.append(h)

    json.dump(dict(threshold=thr, n_null=int(nv.size), candidates=hits,
                   survivors=survivors),
              open(os.path.join(D.LB, "hunt.json"), "w"), indent=1)
    print(f"\n{len(survivors)} survive the spatial null")
    for h in survivors:
        render(h)


def render(h):
    ours = np.load(os.path.join(D.LB, f"map_{h['tag']}.npy"))
    tex = np.load(os.path.join(D.LB, f"tex_{h['tag']}.npy"))
    meta = json.load(open(os.path.join(D.LB, f"meta_{h['tag']}.json")))
    pub = D.pub_crop(meta)
    bm, legal = masks_for(ours, pub)
    thr = json.load(open(os.path.join(D.LB, "hunt.json")))["threshold"]
    comps, _, hot = find(bm, legal, thr)
    d = D.defog(ours)
    rgb = np.stack([d]*3, -1)
    hp = np.zeros(d.shape, bool)
    hp[:hot.shape[0], :hot.shape[1]] = hot
    rgb[hp] = [255, 180, 40]
    W = 512
    row = Image.new("RGB", (W*4, W+28), (10, 10, 11))
    for i, p in enumerate([tex, pub.astype(np.uint8), d]):
        row.paste(Image.fromarray(p).resize((W, W)).convert("RGB"), (i*W, 28))
    ov = Image.fromarray(rgb).resize((W, W))
    dr = ImageDraw.Draw(ov)
    for c in comps:
        dr.rectangle([c["x0"]*W/1024, c["y0"]*W/1024,
                      (c["x1"]+BOX)*W/1024, (c["y1"]+BOX)*W/1024],
                     outline=(255, 80, 60), width=2)
    row.paste(ov, (3*W, 28))
    ImageDraw.Draw(row).text(
        (8, 7), f"{h['seg'].split('/')[-2]}  aim {h['aim']:.2f}  "
        f"clusters {h['n']}  peak {h['peak']:.3f}  p={h['p']}  |  "
        f"papyrus - published - ours(defog) - candidates",
        fill=(233, 229, 219))
    out = os.path.join(D.LB, f"hunt_{h['tag']}.png")
    row.save(out)
    print(f"  render -> {os.path.relpath(out, D.ROOT)}")


if __name__ == "__main__":
    main()
