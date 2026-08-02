#!/usr/bin/env python3
"""Which published ink maps actually contain ink, and which are silent.

THE QUESTION. All 421 published maps get shown the same way, and the viewer's
default cutoff is each sheet's own top decile -- which paints 10% of ANY sheet,
including one where the model found nothing at all. A relative threshold cannot
tell a page of text from an empty field; it just selects the noisiest tenth.
That is the exact error that produced three letter-sized false candidates in
July. So "does this sheet have ink" has to be asked in ABSOLUTE score units.

WHAT SEPARATES THEM. A map over real text is heavy-tailed and close to bimodal:
a large low-score background plus a confident high-score population. A map the
model had nothing to say about is unimodal and sits low -- it never commits.
Two absolute statistics catch this without any thresholding of our own:

    p99             the 99th percentile of on-sheet score. Confident calls push
                    it toward saturation; a silent map leaves it mid-range.
    conf_frac       fraction of the sheet scoring >= 200/255. This is an
                    ABSOLUTE bar, identical on every sheet, so unlike the top
                    decile it is allowed to come out at zero.

`spread` (p99 - p50) is reported too, because a map can sit high everywhere
without ever separating figure from ground, and that is not ink either.

WE DID NOT MAKE THESE MAPS. All of them are Vesuvius Challenge's published ink
detections. This measures their published output and detects nothing itself.
Scroll data CC BY-NC 4.0, (c) Vesuvius Challenge.

    python3 tools/silent_maps.py --limit 8      # smoke test first
    python3 tools/silent_maps.py
"""
import argparse
import io
import json
import os
import urllib.request

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "public", "ink-maps.json")
OUT = os.path.join(ROOT, "out", "silence")
UA = {"User-Agent": "Mozilla/5.0"}

CONFIDENT = 200      # absolute score bar, same on every sheet
SILENT_P99 = 200     # a map whose top 1% never reaches the bar said nothing


def load(url, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, os.path.basename(url))
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return np.array(Image.open(path))
    data = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=300).read()
    with open(path, "wb") as fh:
        fh.write(data)
    return np.array(Image.open(io.BytesIO(data)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    doc = json.load(open(CATALOG))
    jobs = [(e, m) for e in doc["entries"] for m in e["maps"]]
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"{len(jobs)} published maps across {len(doc['scrolls'])} scrolls\n")

    os.makedirs(OUT, exist_ok=True)
    cache = os.path.join(OUT, "maps")
    rows = []
    for i, (e, m) in enumerate(jobs, 1):
        try:
            a = load(m["url"], cache)
        except Exception as exc:
            print(f"  {e['segment'][:14]}  FETCH FAIL {exc}")
            continue
        if a.ndim == 3:
            a = a[..., 0]
        on = a[a > 0]
        if on.size < 1000:
            print(f"  {e['segment'][:14]}  empty raster -- skipped")
            continue

        p50, p90, p99 = (int(np.percentile(on, q)) for q in (50, 90, 99))
        conf = float((on >= CONFIDENT).mean())
        rows.append(dict(
            scroll=e["scroll"], segment=e["segment"][:14], surface_id=e["id"],
            model=m["model"], voxel_um=e["voxelUm"],
            p50=p50, p90=p90, p99=p99, spread=p99 - p50, max=int(on.max()),
            conf_frac=round(conf, 5),
            sheet_mpx=round(float(on.size) / 1e6, 2),
            silent=bool(p99 < SILENT_P99)))
        if i % 25 == 0 or args.limit:
            r = rows[-1]
            print(f"  [{i:3d}/{len(jobs)}] {r['scroll']:12s} {r['segment']}  "
                  f"p50={r['p50']:3d} p99={r['p99']:3d} "
                  f"conf={100*r['conf_frac']:5.2f}%  "
                  f"{'SILENT' if r['silent'] else ''}")

    if not rows:
        print("\nnothing measured")
        return

    by_scroll = {}
    for r in rows:
        s = by_scroll.setdefault(r["scroll"], [])
        s.append(r)

    print(f"\n{'scroll':13s} {'maps':>5s} {'silent':>7s} "
          f"{'med p99':>8s} {'med conf%':>10s}")
    for s in sorted(by_scroll):
        g = by_scroll[s]
        print(f"{s:13s} {len(g):5d} {sum(x['silent'] for x in g):7d} "
              f"{int(np.median([x['p99'] for x in g])):8d} "
              f"{100*float(np.median([x['conf_frac'] for x in g])):10.2f}")

    n_silent = sum(r["silent"] for r in rows)
    summary = dict(
        maps=len(rows), silent=n_silent,
        confident_bar=CONFIDENT, silent_rule=f"p99 < {SILENT_P99}",
        note="Absolute-score audit of Vesuvius Challenge's published ink "
             "detections. A relative cutoff (top decile) calls 10% of every "
             "sheet whether or not the model found anything, so silence can "
             "only be seen in absolute units. No ink is detected here.",
        maps_detail=rows)
    path = os.path.join(OUT, "silence.json")
    json.dump(summary, open(path, "w"), indent=1)
    print(f"\n{n_silent}/{len(rows)} maps are silent by p99 < {SILENT_P99}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
