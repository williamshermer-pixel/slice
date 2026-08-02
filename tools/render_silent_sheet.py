#!/usr/bin/env python3
"""Render the papyrus under a SILENT published ink map, so it can be looked at.

THE QUESTION THIS ANSWERS. 26 of Vesuvius Challenge's 420 published ink maps
are silent in absolute terms -- their top 1% of scores never reaches the
confidence bar. Six of the most silent are freshly segmented Scroll 1 sheets at
2.258 um, which is 6.6 voxels across a 15 um ink layer. Under-sampling is
therefore NOT available as an excuse there.

So either the papyrus is blank, or the model failed to recover ink that is
present. Their own open-problems doc names that distinction as unsolved. On
Scroll 1 -- 3.00 mm hand, the one sheet in the library where letterforms
resolve -- it is settled by LOOKING, which costs nothing and needs no model.

This renders the surface volume itself at the measured ink band, next to the
silent map drawn on the same footprint. No detector runs. Nothing is claimed.

READ BEFORE CHANGING
--------------------
  ink band 27-89    Reading the stack centre instead cost AUC 0.654 vs 0.944
                    against published calls -- the largest single effect in
                    this project. The layer matters more than anything else
                    here, so a mean over the band is taken, not a mid slice.

  anisotropic       Surface pyramids keep EVERY sheet layer at every level and
                    downsample only in-plane. Depth indices are level-0 indices
                    at all levels; using the in-plane factor on depth silently
                    clamps a 116-layer sheet to its first few layers.

  chunk = column    A surface chunk is [depth, 128, 128] -- the entire depth
                    stack of a tile in one object. So the band is free once the
                    tile is fetched, and the cost is set by AREA alone.

  sparse            Chunks outside the mask were never written; S3 404s and the
                    array fills from fill_value. Absent is not an error.

    python3 tools/render_silent_sheet.py --segment 20260603024952
"""
import argparse
import concurrent.futures as cf
import json
import os
import urllib.error
import urllib.request

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "public", "ink-maps.json")
OUT = os.path.join(ROOT, "out", "silence", "renders")
UA = {"User-Agent": "Mozilla/5.0"}
BAND = (27, 90)          # measured ink band, half-open
CHUNK = 128


def get(url, timeout=180):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def render(volume_url, level, band=BAND, workers=12):
    """Mean over the ink band of a whole level, assembled from chunks."""
    za = json.loads(get(f"{volume_url}/{level}/.zarray").decode())
    depth, height, width = za["shape"]
    cz, cy, cx = za["chunks"]
    assert za["dtype"] == "|u1" and za["compressor"] is None, za
    lo, hi = min(band[0], depth), min(band[1], depth)
    if hi <= lo:
        lo, hi = 0, depth

    gy, gx = -(-height // cy), -(-width // cx)
    out = np.zeros((height, width), np.float32)
    present = np.zeros((gy, gx), bool)

    def tile(job):
        i, j = job
        try:
            raw = get(f"{volume_url}/{level}/0.{i}.{j}"
                      if False else f"{volume_url}/{level}/{0}/{i}/{j}")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return i, j, None      # sparse: never written
            raise
        a = np.frombuffer(raw, np.uint8)
        if a.size != cz * cy * cx:
            return i, j, None
        return i, j, a.reshape(cz, cy, cx)[lo:hi].mean(0)

    jobs = [(i, j) for i in range(gy) for j in range(gx)]
    with cf.ThreadPoolExecutor(workers) as ex:
        for i, j, m in ex.map(tile, jobs):
            if m is None:
                continue
            y0, x0 = i * cy, j * cx
            h = min(cy, height - y0)
            w = min(cx, width - x0)
            out[y0:y0 + h, x0:x0 + w] = m[:h, :w]
            present[i, j] = True
    return out, present, (depth, height, width)


def stretch(a):
    """Percentile window with the mask excluded -- 0 is air, and counting it
    pins the low end and renders near-black mush."""
    v = a[a > 0]
    if v.size < 100:
        return np.zeros(a.shape, np.uint8)
    lo, hi = np.percentile(v, 1), np.percentile(v, 99)
    if hi <= lo:
        hi = lo + 1
    return np.clip((a - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segment", required=True)
    ap.add_argument("--level", type=int, default=4)
    ap.add_argument("--max-width", type=int, default=1500)
    args = ap.parse_args()

    doc = json.load(open(CATALOG))
    ent = [e for e in doc["entries"] if e["segment"].startswith(args.segment)]
    if not ent:
        raise SystemExit(f"no catalog entry for {args.segment}")
    os.makedirs(OUT, exist_ok=True)

    for e in ent:
        tag = f"{e['scroll']}-{e['segment'][:14]}-{e['voxelUm']:g}um"
        print(f"\n=== {tag}\n    {e['volume']}")
        ct, present, shape = render(e["url"], args.level)
        stored = int(present.sum())
        print(f"    level {args.level}: {shape}  tiles {stored}/{present.size} stored")
        img = Image.fromarray(stretch(ct))
        if img.width > args.max_width:
            k = args.max_width / img.width
            img = img.resize((args.max_width, max(1, int(img.height * k))),
                             Image.LANCZOS)
        p = os.path.join(OUT, f"{tag}-ct.png")
        img.save(p)
        print(f"    CT  -> {p}  ({img.width}x{img.height})")

        for m in e["maps"]:
            cached = os.path.join(ROOT, "out", "silence", "maps",
                                  os.path.basename(m["url"]))
            if not os.path.exists(cached):
                continue
            a = np.array(Image.open(cached))
            if a.ndim == 3:
                a = a[..., 0]
            on = a[a > 0]
            p99 = int(np.percentile(on, 99)) if on.size else 0
            mi = Image.fromarray(a)
            if mi.width > args.max_width:
                k = args.max_width / mi.width
                mi = mi.resize((args.max_width, max(1, int(mi.height * k))),
                               Image.LANCZOS)
            q = os.path.join(OUT, f"{tag}-map-{m['model'][-22:]}.png")
            mi.save(q)
            print(f"    MAP -> {q}  p99={p99} "
                  f"{'SILENT' if p99 < 200 else 'confident'}")


if __name__ == "__main__":
    main()
