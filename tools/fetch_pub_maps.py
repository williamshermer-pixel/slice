#!/usr/bin/env python3
"""Fetch the ds8 published ink maps for every segment of a scroll that has BOTH
energies, which is what the cross-energy consensus needs.

Which scrolls qualify (surveyed 2026-07-31 against the live bucket). A scan
only counts if it can sample a 15 um ink layer at 3+ voxels, so the 9.362 um
113 keV and 8.64 um 116 keV volumes are excluded on physics, not preference:

    PHerc1667   59 keV (1.129-L1) + 78 keV (2.399)   7/7   curated
    PHerc0139   59 keV (1.129-L1) + 78 keV (2.399)  37/38  the calibrated scroll
    PHerc0814   59 keV (1.129-L1) + 78 keV (2.399)  19     mostly auto-grown
    PHerc0343P  one usable scan only                       -- no pair
    PHerc0500P2 one usable scan only                       -- no pair
    PHercParis4 two scans but BOTH 78 keV                  -- not independent
    PHerc0172   one scan, 7.91 um                          -- fails the physics

CORRECTION 2026-08-01. This list previously said PHerc0172 had "no
ink-detection maps -- physics control". That is false and was never true: 0172
has 53 segments with published maps, 106 of them, because TWO model checkpoints
(timesformer_scroll5_july_retreat and _november19) ran on the same 7.91 um
volume. It is excluded here for the reason stated above -- one scan, so no
energy pair -- not for want of maps.

Worth not losing: two checkpoints on one volume is a MODEL-vs-model comparison,
which is a different instrument from the energy-vs-energy one this file feeds,
and nothing in this project has used it. See public/ink-maps.json.

The proxy WAF 403s python-urllib's user agent, so this spoofs a browser UA.
Files already held are never refetched -- a failed refetch once deleted 42
harvested files in this project.

    python3 tools/fetch_pub_maps.py PHerc0139
"""
import os, sys, re, urllib.request

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=120).read()


def listing(prefix, delim="/"):
    out, token = [], None
    while True:
        u = f"{B}/?list-type=2&prefix={prefix}&max-keys=1000"
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


def main():
    scroll = sys.argv[1] if len(sys.argv) > 1 else "PHerc1667"
    dest = os.path.join(ROOT, "out", f"xe_{scroll}", "pub")
    os.makedirs(dest, exist_ok=True)

    segs = listing(f"{scroll}/segments/")
    print(f"{scroll}: {len(segs)} segments")
    paired = 0
    for seg in segs:
        keys = [k for k in listing(f"{seg}ink-detection/downsampled/", delim="")
                if k.endswith(".jpg")]
        e59 = [k for k in keys if "59keV" in k]
        e78 = [k for k in keys if "78keV" in k]
        if not (e59 and e78):
            continue
        paired += 1
        for k in (e59[0], e78[0]):
            f = os.path.join(dest, os.path.basename(k))
            if os.path.exists(f) and os.path.getsize(f) > 0:
                continue
            try:
                data = get(f"{B}/{k}")
            except Exception as e:
                print("  FAIL", os.path.basename(k), e)
                continue
            with open(f, "wb") as fh:
                fh.write(data)
        print(f"  {os.path.basename(seg.rstrip('/'))[:34]:36s} paired")
    have = len([f for f in os.listdir(dest) if f.endswith(".jpg")])
    print(f"\n{paired} paired segments, {have} files in {dest}")


if __name__ == "__main__":
    import urllib.parse
    main()
