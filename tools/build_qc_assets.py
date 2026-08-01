#!/usr/bin/env python3
"""Bake the consensus labels into web assets for the QC overlay page.

The label rasters are 10-14 MP each and 10 MB total as zarr. For a browser QC
tool nobody needs full resolution: a letter is 90 px at ds8, so a 1400 px-wide
view still shows disagreement at letter scale, and the whole scroll fits in a
couple of MB.

Encoding: one PNG per segment, with the CODE stored in the red channel
(0/1/2/3) rather than a colour. The page recolours in canvas, so the legend can
be toggled and the palette can change without regenerating anything. Green
carries a downsample-safe flag: 255 where the block contained ANY disputed
pixel, so a 4x downsample cannot hide disagreement by majority-voting it away.
That matters -- the whole point of the page is finding disagreement.

    python3 tools/build_qc_assets.py
"""
import glob, json, os, zlib
import numpy as np
from scipy import ndimage
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "out", "consensus", "PHerc0139")
DEST = os.path.join(ROOT, "public", "qc")
MAXW = 1400
DS8_UM = 18.064


def read_zarr(path):
    z = json.load(open(os.path.join(path, ".zarray")))
    cert = json.load(open(os.path.join(path, ".zattrs")))
    ch, sh = z["chunks"], z["shape"]
    gy, gx = -(-sh[0] // ch[0]), -(-sh[1] // ch[1])
    a = np.zeros(sh, np.uint8)
    for i in range(gy):
        for j in range(gx):
            f = os.path.join(path, f"{i}.{j}")
            if not os.path.exists(f):
                continue
            b = np.frombuffer(zlib.decompress(open(f, "rb").read()),
                              np.uint8).reshape(ch)
            h = min(ch[0], sh[0] - i * ch[0])
            w = min(ch[1], sh[1] - j * ch[1])
            a[i * ch[0]:i * ch[0] + h, j * ch[1]:j * ch[1] + w] = b[:h, :w]
    return a, cert


SEGFULL = {}


def _load_segfull():
    """Bucket paths need the full segment directory name, not the 14-digit id."""
    import urllib.request, re as _re
    B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
    req = urllib.request.Request(
        f"{B}/?list-type=2&prefix=PHerc0139/segments/&delimiter=/&max-keys=1000",
        headers={"User-Agent": "Mozilla/5.0"})
    x = urllib.request.urlopen(req, timeout=60).read().decode()
    for p in _re.findall(r"<Prefix>([^<]*)</Prefix>", x):
        name = p.rstrip("/").split("/")[-1]
        if len(name) >= 14:
            SEGFULL[name[:14]] = name


def main():
    _load_segfull()
    os.makedirs(DEST, exist_ok=True)
    index = []
    for p in sorted(glob.glob(os.path.join(SRC, "*.zarr"))):
        seg = os.path.basename(p)[:-5]
        lab, cert = read_zarr(p)
        H, W = lab.shape
        f = max(1, int(np.ceil(W / MAXW)))
        # block-reduce by f: mode-ish for the base code, but ANY-disputed wins
        Hc, Wc = (H // f) * f, (W // f) * f
        blk = lab[:Hc, :Wc].reshape(Hc // f, f, Wc // f, f)
        disputed = (blk == 3).any(axis=(1, 3))
        ink = (blk == 1).any(axis=(1, 3))
        blank = (blk == 2).any(axis=(1, 3))
        base = np.zeros(disputed.shape, np.uint8)
        base[blank] = 2
        base[ink] = 1          # ink outranks blank in a mixed block
        base[disputed & ~ink] = 3
        rgb = np.zeros(base.shape + (3,), np.uint8)
        rgb[..., 0] = base
        rgb[..., 1] = np.where(disputed, 255, 0)
        Image.fromarray(rgb).save(os.path.join(DEST, f"{seg}.png"),
                                  optimize=True)

        # The work queue: the biggest contiguous disagreement regions, so an
        # annotator gets somewhere to GO rather than a picture to look at.
        # Coordinates are emitted in SURFACE-VOLUME level-0 space (label ds8 x8)
        # because that is what the viewer takes, and the published ink map is
        # written on the surface volume's own canvas -- verified across all 37
        # segments to within +/-16 px on canvases of 20-40k px, i.e. ~2% of a
        # letter.
        lb, n = ndimage.label(lab == 3)
        clusters = []
        if n:
            areas = ndimage.sum(np.ones_like(lb, bool), lb, range(1, n + 1))
            order = np.argsort(areas)[::-1][:12]
            cents = ndimage.center_of_mass(lab == 3, lb,
                                           [int(o) + 1 for o in order])
            for k, o in enumerate(order):
                cy, cx = cents[k]
                px_mm2 = (DS8_UM / 1000.0) ** 2
                clusters.append(dict(
                    y=int(round(cy)) * 8, x=int(round(cx)) * 8,
                    area_mm2=round(float(areas[o]) * px_mm2, 2),
                    letters=round(float(areas[o]) /
                                  (cert["letter_height_px"] ** 2), 1)))

        a = cert["agreement"]
        c = cert["counts_pct_of_canvas"]
        index.append(dict(
            segment=seg, segment_full=SEGFULL.get(seg, seg),
            w=int(base.shape[1]), h=int(base.shape[0]),
            downsample=f, um_per_px=round(DS8_UM * f, 2),
            letter_px=round(cert["letter_height_px"] / f, 1),
            pct=c, shared_sheet_pct=a["shared_sheet_pct"],
            pearson_r=a["highpass_pearson_r"], jaccard=a["jaccard"],
            null=a["jaccard_spatial_null"], enrichment=a["enrichment_over_null"],
            p=a["p_vs_rolled_null"],
            clusters=clusters,
            surface_id=f"0139-{seg}",
            registration=cert["registration"].get("measured_this_segment", {}),
            sources=cert["sources"]))
        print(f"{seg}  {base.shape[1]}x{base.shape[0]} (1/{f})  "
              f"ink {c['ink']:.2f}%  disputed {c['disputed']:.2f}%")

    index.sort(key=lambda r: -r["pct"]["disputed"])
    json.dump(dict(
        scroll="PHerc0139", letter_mm=1.61, n=len(index),
        note="code in RED channel (0 unlabelled, 1 ink, 2 blank, 3 disputed); "
             "GREEN 255 marks any block containing a disputed pixel, so "
             "downsampling cannot hide disagreement",
        segments=index), open(os.path.join(DEST, "index.json"), "w"), indent=1)
    mb = sum(os.path.getsize(os.path.join(DEST, f))
             for f in os.listdir(DEST)) / 1e6
    print(f"\n{len(index)} segments -> {DEST}  ({mb:.1f} MB total)")


if __name__ == "__main__":
    main()
