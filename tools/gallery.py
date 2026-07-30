"""GALLERY — put every candidate that ever scored in front of human eyes.

Statistics have now twice said "something is here" when nothing was. A
correlation of +0.39 is an abstraction; a picture of the detector next to the
published ink is not. This renders every candidate that ever got a hit, on the
same segments, so they can be compared by looking.

Each candidate gets a row per segment with four panels:

  CT SLICE     the flattened sheet as it actually is
  DETECTOR     what the candidate outputs
  INK          the published ink map — the answer key
  OVERLAY      detector in RED, ink in GREEN. Agreement shows up YELLOW.

The overlay is the one to read. If a detector were finding letters, the letter
strokes would be yellow. Red-only means it is firing where there is no ink;
green-only means it is missing ink that is there.

Usage: python3 gallery.py [n_candidates] [n_segments]
"""
import os, sys, json, glob
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

_argv, sys.argv = sys.argv, [sys.argv[0]]
import dogs as D
sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "gallery")
os.makedirs(OUT, exist_ok=True)
S = 300


def n8(a, lo=2, hi=98):
    a = np.asarray(a, np.float32)
    l, h = np.percentile(a, lo), np.percentile(a, hi)
    return np.clip((a-l)/max(h-l, 1e-6)*255, 0, 255).astype(np.uint8)


def collect(n=8):
    """Every distinct candidate that ever scored, across all rounds."""
    recs = []
    for f in glob.glob(os.path.join(HERE, "..", "out", "dogs", "**", "dogs_w*.jsonl"),
                       recursive=True):
        for line in open(f):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("stage") in ("tested", "gated") and r.get("heldout_median", 0) >= 0.20:
                recs.append(r)
    # dedupe by feature set + weight signature
    seen, out = set(), []
    for r in sorted(recs, key=lambda r: -r["heldout_median"]):
        v = r["variant"]
        # dedupe on the FEATURE SET alone. Keying on weights too returns the
        # same family eight times with cosmetic weight differences, which
        # tells a human nothing.
        k = tuple(sorted(v["features"]))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
        if len(out) >= n:
            break
    return out


def panel_row(tile, f, s_score):
    """slice | detector | ink | overlay, aligned on the ink grid."""
    fb, sub = P._align(f, tile)
    if fb is None:
        return None
    slc, _ = P._align(P.mid_image(tile, 8), tile)
    det = n8(fb)
    ink = np.clip(sub, 0, 255).astype(np.uint8)
    rgb = np.dstack([det, ink, np.zeros_like(det)])
    imgs = [Image.fromarray(n8(slc)).convert("RGB"),
            Image.fromarray(det).convert("RGB"),
            Image.fromarray(ink).convert("RGB"),
            Image.fromarray(rgb)]
    row = Image.new("RGB", (4*S+30, S), (10, 10, 11))
    for i, im in enumerate(imgs):
        row.paste(im.resize((S, S), Image.LANCZOS), (i*(S+10), 0))
    return row


def main(ncand=8, nseg=3):
    cands = collect(ncand)
    print(f"{len(cands)} distinct candidates that ever scored >= 0.20\n")
    if not cands:
        print("none"); return

    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    rng = np.random.default_rng(2026)
    # the SAME segments for every candidate, so rows are comparable
    segs = P.warm([held[i] for i in rng.permutation(len(held))[:nseg*8]], verbose=False)
    scored = []
    for t in segs:
        tile = P.load_tile(t)
        if tile is None:
            continue
        c = P.crop_coverage(t)
        if c is not None and c > 0.02:      # must actually contain text to judge
            scored.append((c, tile))
    # richest text first — the easiest possible case for a real detector
    scored.sort(key=lambda x: -x[0])
    tiles = [t for _, t in scored[:nseg]]
    print(f"judging on {len(tiles)} segments with real text\n")

    index = []
    for ci, r in enumerate(cands):
        V = r["variant"]
        name = "+".join(V["features"])
        rows = []
        for tile in tiles:
            try:
                f = D.feature_map(tile, V)
            except Exception:
                f = None
            if f is None:
                continue
            row = panel_row(tile, f, r)
            if row is not None:
                rows.append((row, tile["scroll"]))
        if not rows:
            print(f"  [{ci}] {name}: no renderable segments")
            continue
        H = 34
        sheet = Image.new("RGB", (4*S+30, H + len(rows)*(S+22)), (10, 10, 11))
        d = ImageDraw.Draw(sheet)
        g = lambda k: ("%.3f" % r[k]) if r.get(k) is not None else "--"
        d.text((6, 5), f"{name}   weights {[round(float(w),2) for w in V['weights']]}",
               fill=(233, 229, 219))
        d.text((6, 19), f"raw held-out {r['heldout_median']:+.3f}   blank {g('negative_control')}"
                        f"   blind {g('physics_control')}   partial {g('partial_r')}",
               fill=(200, 151, 31))
        for i, (row, scroll) in enumerate(rows):
            y = H + i*(S+22)
            sheet.paste(row, (0, y))
            d.text((6, y+S+4), f"{scroll}     "
                   f"SLICE          DETECTOR        PUBLISHED INK    "
                   f"OVERLAY (red=detector, green=ink, yellow=agreement)",
                   fill=(139, 139, 148))
        p = os.path.join(OUT, f"cand{ci:02d}_{name.replace('+','_')[:40]}.png")
        sheet.save(p)
        index.append((p, name, r))
        print(f"  [{ci}] {name:38s} raw {r['heldout_median']:+.3f}  -> {os.path.basename(p)}")

    json.dump([{"file": os.path.basename(p), "features": n,
                "raw": r["heldout_median"], "blank": r.get("negative_control"),
                "blind": r.get("physics_control"), "partial": r.get("partial_r")}
               for p, n, r in index],
              open(os.path.join(OUT, "index.json"), "w"), indent=1)
    print(f"\n{len(index)} sheets in {OUT}")
    print("\nRead the OVERLAY column. Yellow = the detector fired where the ink is.")
    return index


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 8, int(a[1]) if len(a) > 1 else 3)
