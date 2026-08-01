#!/usr/bin/env python3
"""Render a consensus label array so a human can see what the deliverable says.

The labels are the product; this is the picture of them. Four codes, four
colours, on the carbonized-papyrus palette:

    papyrus white   1  consensus ink     both scans call it
    ochre           3  disputed          exactly one scan calls it
    slate           2  consensus blank   neither, and clear of both keep-outs
    void            0  unlabelled        not covered by both, or edge keep-out

Read it as a map of how much two scans of the same papyrus actually agree.
White is where two energies and two recipes concur.
Ochre is where one scan saw something the other did not — shipped as its own
code rather than silently resolved, because resolving it would be exactly the
arbitrary call the method exists to avoid.

    SCROLL=PHerc0139 python3 tools/render_consensus.py 20260302000001
    SCROLL=PHerc1667 python3 tools/render_consensus.py            # all
"""
import glob, json, os, sys, zlib
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "out", "consensus")
SCROLL = os.environ.get("SCROLL", "PHerc0139")

VOID = (10, 10, 11)
SLATE = (38, 38, 43)
OCHRE = (200, 151, 31)
PAPYRUS = (233, 229, 219)
ASH = (139, 139, 148)
COLOR = {0: VOID, 1: PAPYRUS, 2: SLATE, 3: OCHRE}


def read_zarr(path):
    z = json.load(open(os.path.join(path, ".zarray")))
    cert = json.load(open(os.path.join(path, ".zattrs")))
    ch, sh = z["chunks"], z["shape"]
    gy = -(-sh[0] // ch[0])
    gx = -(-sh[1] // ch[1])
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


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for path in sorted(glob.glob(os.path.join(SRC, SCROLL, "*.zarr"))):
        seg = os.path.basename(path)[:-5]
        if only and only not in seg:
            continue
        lab, cert = read_zarr(path)
        rgb = np.zeros(lab.shape + (3,), np.uint8)
        for code, col in COLOR.items():
            rgb[lab == code] = col

        im = Image.fromarray(rgb)
        im.thumbnail((1700, 1000), Image.NEAREST)
        pad, top, cap = 16, 44, 40
        canvas = Image.new("RGB", (im.width + 2 * pad, top + im.height + cap),
                           VOID)
        dr = ImageDraw.Draw(canvas)
        canvas.paste(im, (pad, top))
        a = cert["agreement"]
        c = cert["counts_pct_of_canvas"]
        dr.text((pad, 10),
                f"{cert['scroll']}  {seg}   CROSS-ENERGY CONSENSUS LABELS   "
                f"{cert['resolution_um_per_px']} um/px   "
                f"letter {cert['letter_height_mm']} mm = "
                f"{cert['letter_height_px']} px", fill=ASH)
        dr.text((pad, 25),
                f"59 keV vs 78 keV — cross-energy, cross-recipe   "
                f"rho {a['letterscale_spearman_r']}   "
                f"jaccard {a['jaccard']} vs null {a['jaccard_spatial_null']}   "
                f"p {a['p_vs_rolled_null']}", fill=ASH)
        y = top + im.height + 8
        for i, (lbl, col) in enumerate([
                ("WHITE  consensus ink (both scans)  %.1f%%" % c["ink"], PAPYRUS),
                ("OCHRE  disputed (one scan)  %.1f%%" % c["disputed"], OCHRE),
                ("SLATE  certified blank  %.1f%%" % c["blank"], SLATE),
                ("VOID   unlabelled  %.1f%%" % c["unlabelled"], ASH)]):
            x = pad + i * (im.width // 4)
            dr.rectangle([x, y + 2, x + 10, y + 12], fill=col)
            dr.text((x + 16, y), lbl, fill=ASH)
        out = os.path.join(SRC, f"labels_{cert['scroll']}_{seg}.png")
        canvas.save(out)
        print("wrote", out)


if __name__ == "__main__":
    main()
