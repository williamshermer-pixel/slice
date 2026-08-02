#!/usr/bin/env python3
"""Where Scroll 5's two published models disagree with each other.

THE OPENING. PHerc0172 (Scroll 5) carries 53 segments with TWO published ink
maps each -- `timesformer_scroll5_july_retreat` and `..._november19` -- both
computed on the SAME 7.91 um volume. That is not two energies and not two
scans: it is one piece of papyrus scored twice by two checkpoints. Nothing in
this project, and nothing published, has measured where they differ.

WHY IT MATTERS. ScrollPrize's own open-problems doc names distinguishing
"no ink" from "no ink recovered yet" as unsolved. Two independent models over
identical input is the cleanest handle on that anyone has: where both are
confident, the call is about the papyrus; where they split, the call is about
the model, and that is exactly the region a human should be asked to look at.

WE DID NOT MAKE THESE MAPS. Both are Vesuvius Challenge's. This tool measures
them and claims nothing about ink it has found. Scroll data CC BY-NC 4.0.

THE STATISTICS, AND THE MISTAKES THEY ENCODE
--------------------------------------------
Every one of these is a bug this project already shipped once:

  matched call density  Each map is thresholded at ITS OWN top decile, so both
                        call the same NUMBER of pixels. A null that lets call
                        density drift inflated enrichment ~6x here before.

  rolled spatial null   The null rolls one map by a large offset. That
                        preserves its histogram and autocorrelation exactly
                        while destroying its registration to the papyrus. A
                        null that was secretly the identity operation is how
                        three letter-sized candidates survived in July.

  24 rolls              p floor 0.042. NULL_N=16 with a p<=0.05 flag was
                        arithmetically unreachable -- a test that could never
                        fire.

  letters, not pixels   Disagreement clusters are reported in units of Scroll
                        5's letter area. Connected components of binarised maps
                        run 3-5x small (fragments, not letters), so the hand is
                        taken from the band-FWHM ruler, not from components.

    python3 tools/model_disagreement_0172.py
    python3 tools/model_disagreement_0172.py --limit 5      # smoke test first
"""
import argparse
import io
import json
import os
import urllib.request

import numpy as np
from PIL import Image
from scipy import ndimage

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "public", "ink-maps.json")
OUT = os.path.join(ROOT, "out", "disagree_0172")
UA = {"User-Agent": "Mozilla/5.0"}

SCROLL = "PHerc0172"
N_ROLL = 24                 # p floor 1/24 = 0.042
DS8_UM = 7.91 * 8           # published maps are ds8 of a 7.91 um volume
HAND_MM = 1.63              # placeholder until measure_hand.py runs on 0172


def fetch(url, cache_dir):
    """Never refetch a held file -- a failed refetch once deleted 42 files."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, os.path.basename(url))
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return np.array(Image.open(path))
    data = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=300).read()
    with open(path, "wb") as fh:
        fh.write(data)
    return np.array(Image.open(io.BytesIO(data)))


def calls(a, sheet):
    """Top decile of this map's own on-sheet scores. Matched density by design."""
    v = a[sheet]
    if v.size == 0:
        return np.zeros_like(a, bool), 0
    t = int(np.percentile(v, 90))
    return (a >= t) & sheet, t


def jaccard(x, y):
    u = np.count_nonzero(x | y)
    return float(np.count_nonzero(x & y)) / u if u else 0.0


def rolled_null(x, y, rng):
    """Jaccard against rolled copies of y. Registration destroyed, stats kept."""
    h, w = y.shape
    out = []
    for _ in range(N_ROLL):
        dy = int(rng.integers(h // 8, h - h // 8))
        dx = int(rng.integers(w // 8, w - w // 8))
        out.append(jaccard(x, np.roll(np.roll(y, dy, 0), dx, 1)))
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    doc = json.load(open(CATALOG))
    sheets = [e for e in doc["entries"]
              if e["scroll"] == SCROLL and len(e["maps"]) >= 2]
    if args.limit:
        sheets = sheets[:args.limit]
    print(f"{len(sheets)} Scroll 5 sheets with two model checkpoints\n")

    os.makedirs(OUT, exist_ok=True)
    cache = os.path.join(OUT, "maps")
    rng = np.random.default_rng(20260801)
    letter_px = (HAND_MM * 1000.0) / DS8_UM
    letter_area = letter_px ** 2
    rows = []

    for i, e in enumerate(sheets, 1):
        seg = e["segment"][:14]
        m0, m1 = e["maps"][0], e["maps"][1]
        try:
            a = fetch(m0["url"], cache)
            b = fetch(m1["url"], cache)
        except Exception as exc:
            print(f"  {seg}  FETCH FAIL {exc}")
            continue
        if a.shape != b.shape:
            print(f"  {seg}  SHAPE MISMATCH {a.shape} vs {b.shape} -- skipped")
            continue

        # On-sheet mask: the maps are masked, and 0 is off-sheet. Counting it
        # drags every percentile onto background.
        sheet = (a > 0) | (b > 0)
        if sheet.mean() < 0.01:
            print(f"  {seg}  empty map -- skipped")
            continue

        ca, ta = calls(a, sheet)
        cb, tb = calls(b, sheet)
        j = jaccard(ca, cb)
        null = rolled_null(ca, cb, rng)
        p = float((null >= j).sum() + 1) / (N_ROLL + 1)
        enrich = j / max(float(null.mean()), 1e-9)

        only_a = ca & ~cb
        only_b = cb & ~ca
        both = ca & cb
        n_called = np.count_nonzero(ca | cb)
        split = (np.count_nonzero(only_a | only_b) / n_called) if n_called else 0.0

        # Biggest contested regions, in letters.
        lab, n = ndimage.label(only_a | only_b)
        big = []
        if n:
            areas = ndimage.sum(np.ones_like(lab, bool), lab, range(1, n + 1))
            order = np.argsort(areas)[::-1][:5]
            cents = ndimage.center_of_mass(
                only_a | only_b, lab, [int(o) + 1 for o in order])
            for k, o in enumerate(order):
                if areas[o] < letter_area * 0.5:
                    break
                cy, cx = cents[k]
                big.append(dict(y=int(cy * 8), x=int(cx * 8),
                                letters=round(float(areas[o]) / letter_area, 1)))

        rows.append(dict(
            segment=seg, segment_full=e["segment"], surface_id=e["id"],
            models=[m0["model"], m1["model"]], thresholds=[ta, tb],
            jaccard=round(j, 4), null_mean=round(float(null.mean()), 4),
            enrichment=round(float(enrich), 2), p=round(p, 3),
            agree_pct=round(100 * np.count_nonzero(both) / max(n_called, 1), 1),
            split_pct=round(100 * split, 1),
            sheet_cm2=round(float(sheet.sum()) * (DS8_UM / 1e4) ** 2, 2),
            contested=big))
        print(f"  [{i:2d}/{len(sheets)}] {seg}  agree {rows[-1]['agree_pct']:5.1f}%"
              f"  J={j:.3f} vs null {null.mean():.3f}"
              f"  x{enrich:5.1f}  p={p:.3f}  contested {len(big)}")

    if not rows:
        print("\nno sheets measured")
        return

    js = np.array([r["jaccard"] for r in rows])
    ag = np.array([r["agree_pct"] for r in rows])
    en = np.array([r["enrichment"] for r in rows])
    summary = dict(
        scroll=SCROLL, sheets=len(rows), rolls=N_ROLL,
        median_jaccard=round(float(np.median(js)), 4),
        median_agree_pct=round(float(np.median(ag)), 1),
        median_enrichment=round(float(np.median(en)), 2),
        n_significant=int(sum(r["p"] <= 1.0 / (N_ROLL + 1) for r in rows)),
        contested_sheets=int(sum(1 for r in rows if r["contested"])),
        note="Both maps are Vesuvius Challenge's published ink detections on "
             "one 7.91 um volume; this measures where the two checkpoints "
             "differ. No ink was detected here. Each map thresholded at its "
             "own top decile so call density is matched; null rolls one map, "
             "preserving its histogram and autocorrelation while destroying "
             "registration.",
        segments=rows)
    path = os.path.join(OUT, "disagreement.json")
    json.dump(summary, open(path, "w"), indent=1)

    print(f"\n{len(rows)} sheets")
    print(f"  median agreement between the two models  {summary['median_agree_pct']}%")
    print(f"  median Jaccard {summary['median_jaccard']} "
          f"(enrichment x{summary['median_enrichment']} over rolled null)")
    print(f"  significant at the {1/(N_ROLL+1):.3f} floor: "
          f"{summary['n_significant']}/{len(rows)}")
    print(f"  sheets with a letter-scale contested region: "
          f"{summary['contested_sheets']}")
    print(f"\n-> {path}")


if __name__ == "__main__":
    main()
