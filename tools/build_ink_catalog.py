#!/usr/bin/env python3
"""Catalog every published ink detection in the bucket, and the sheet it belongs on.

There are 255 of them across 7 scrolls (surveyed live 2026-08-01). This repo had
already harvested that exact list into `tools/nightshift_targets.json` and then
wired the viewer to 38 of it. This tool exists so the viewer sees all of it.

THE JOIN, and why it needs no registration
------------------------------------------
An ink map's filename contains, verbatim, the name of the surface volume it was
computed on:

    PHerc0139-20250108000000-1.129um-0.22m-59keV-volume-20260413113053-L1-…-ds8.jpg
                             ^--------- surface-volumes/<this>.zarr ---------^

So the join is substring containment against the segment's own
`surface-volumes/` listing. No guessing which flattening a map belongs to, and
no way to silently pair a map with the wrong sheet.

The map is written on that volume's own canvas (`.zattrs:canvas_size`, [x, y] at
level 0), so a map pixel maps to the sheet by a pure scale. We deliberately do
NOT record a downsample factor here: the true factor is 8.0006, not 8, and the
browser can compute it exactly as `canvas_x / image.width` once the image
lands. Baking "8" is how you get an overlay that drifts a letter-width across a
30k-pixel sheet.

WHAT IS AND IS NOT REDISTRIBUTED
--------------------------------
This emits URLs only — no pixels. The browser fetches the ds8 JPEG straight from
the public bucket (verified `Access-Control-Allow-Origin: *`), which keeps the
CC BY-NC scroll data out of this repo and keeps the read path client-side.

    python3 tools/build_ink_catalog.py
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.parse
import urllib.request

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0"}
DEST = os.path.join(ROOT, "public", "ink-maps.json")


def get(url, timeout=120):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def listing(prefix, delim="/"):
    out, token = [], None
    while True:
        u = f"{B}/?list-type=2&prefix={urllib.parse.quote(prefix)}&max-keys=1000"
        if delim:
            u += f"&delimiter={delim}"
        if token:
            u += f"&continuation-token={urllib.parse.quote(token, safe='')}"
        x = get(u).decode()
        tag = "Prefix" if delim else "Key"
        out += re.findall(rf"<{tag}>([^<]*)</{tag}>", x)
        m = re.search(r"<NextContinuationToken>([^<]*)<", x)
        if not m:
            break
        token = m.group(1)
    return [p for p in out if p != prefix]


def model_name(basename, volume):
    """The part of an ink-map filename after the volume it was computed on.

    That tail is the only thing distinguishing two maps of the same sheet, and
    on PHerc0172 it is the whole point: two checkpoints, one volume, so the
    disagreement between them is model-vs-model rather than energy-vs-energy.
    """
    tail = basename.split(volume + "-", 1)[-1]
    tail = re.sub(r"\.(jpg|tif)$", "", tail)
    tail = re.sub(r"-ds\d+$", "", tail)
    tail = re.sub(r"-tile\d+-stride\d+$", "", tail)
    return tail or "unnamed"


def do_segment(segpath):
    """-> catalog entry, or (segpath, reason) on a skip."""
    seg = segpath.rstrip("/").split("/")[-1]
    scroll = segpath.split("/")[0]

    keys = listing(f"{segpath}ink-detection/", delim="")
    ds8 = [k for k in keys if k.endswith(".jpg")]
    if not ds8:
        return None, (seg, "no downsampled map")

    vols = [p.rstrip("/").split("/")[-1] for p in
            listing(f"{segpath}surface-volumes/")]
    if not vols:
        return None, (seg, "no surface volume")

    # Longest match first: "…-L1.zarr" and "….zarr" can both be present and the
    # bare one is a prefix of the L1 one. PHerc0814 has exactly this pair.
    stems = sorted((v[:-5] for v in vols if v.endswith(".zarr")),
                   key=len, reverse=True)

    by_volume = {}
    for k in ds8:
        base = os.path.basename(k)
        hit = next((s for s in stems if s in base), None)
        if hit is None:
            continue
        by_volume.setdefault(hit, []).append(
            dict(model=model_name(base, hit), url=f"{B}/{k}"))
    if not by_volume:
        return None, (seg, "no map matched a surface volume")

    out = []
    for stem, maps in by_volume.items():
        url = f"{B}/{segpath}surface-volumes/{stem}.zarr"
        try:
            attrs = json.loads(get(f"{url}/.zattrs", timeout=60).decode())
            zarray = json.loads(get(f"{url}/0/.zarray", timeout=60).decode())
        except Exception as e:
            return None, (seg, f"{stem}: {e}")
        try:
            scale = (attrs["multiscales"][0]["datasets"][0]
                     ["coordinateTransformations"][0]["scale"])
            voxel = round(float(scale[-1]), 4)
        except Exception:
            return None, (seg, f"{stem}: no scale in multiscales")
        canvas = attrs.get("canvas_size")
        shape = zarray["shape"]
        if not canvas or len(shape) != 3:
            return None, (seg, f"{stem}: canvas {canvas} shape {shape}")

        out.append(dict(
            id=f"{scroll}-{seg[:14]}-{stem[:16]}",
            scroll=scroll,
            segment=seg,
            volume=f"{stem}.zarr",
            url=url,
            voxelUm=voxel,
            shape=shape,                 # [layers, y, x] at level 0
            canvas=canvas,               # [x, y] the ink map is drawn on
            maps=sorted(maps, key=lambda m: m["model"]),
        ))
    return out, None


def main():
    only = sys.argv[1:] or None
    scrolls = [p.rstrip("/") for p in listing("", "/") if p.startswith("PHerc")]
    if only:
        scrolls = [s for s in scrolls if s in only]

    entries, skips = [], []
    for scroll in scrolls:
        segs = listing(f"{scroll}/segments/")
        if not segs:
            continue
        with cf.ThreadPoolExecutor(12) as ex:
            results = list(ex.map(do_segment, segs))
        got = [e for ok, _ in results if ok for e in ok]
        bad = [b for _, b in results if b]
        entries += got
        # Only report skips on scrolls that have ink maps at all; a scroll with
        # zero maps is not a failure, it is just not in scope.
        if got:
            skips += [(scroll, s, r) for s, r in bad]
            print(f"{scroll:14s} {len(got):3d} sheets, "
                  f"{sum(len(e['maps']) for e in got):3d} maps")

    entries.sort(key=lambda e: (e["scroll"], e["segment"], e["volume"]))
    doc = dict(
        note="Published ink detections in the Vesuvius Challenge open bucket, "
             "keyed to the surface volume each was computed on. URLs only — no "
             "pixels are redistributed; the browser reads the bucket directly. "
             "Scroll data is CC BY-NC 4.0, © Vesuvius Challenge.",
        generated_by="tools/build_ink_catalog.py",
        sheets=len(entries),
        maps=sum(len(e["maps"]) for e in entries),
        scrolls=sorted({e["scroll"] for e in entries}),
        entries=entries,
    )
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    json.dump(doc, open(DEST, "w"), indent=1)
    print(f"\n{doc['sheets']} sheets, {doc['maps']} maps, "
          f"{len(doc['scrolls'])} scrolls -> {DEST} "
          f"({os.path.getsize(DEST)/1e3:.0f} KB)")
    if skips:
        print(f"\nskipped {len(skips)}:")
        for scroll, seg, reason in skips:
            print(f"  {scroll} {seg[:40]:42s} {reason}")


if __name__ == "__main__":
    main()
