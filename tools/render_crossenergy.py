#!/usr/bin/env python3
"""Evidence render for the PHerc1667 cross-energy consensus.

Law 8: every finding ships as a render before it is believed. The render has
killed two fully-controlled false positives in this project — statistics gate,
human eyes verify.

Two-channel figure, microscopy convention (colour-blind safe, unlike red/green):

    GREEN    59 keV calls it, 78 keV does not
    MAGENTA  78 keV calls it, 59 keV does not
    WHITE    both energies agree — ink confirmed across two independent scans
    grey     shared sheet, neither calls

Panel 1 is the whole segment. Panels 2+ are letter-scale zooms, placed on the
windows carrying the most disagreement, so the question a human has to answer
is concrete: in this box, is the magenta text or is it speckle?

    python3 tools/render_crossenergy.py [segment]
"""
import os, sys, glob, json
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc1667")
_DIRS = {"PHerc1667": "s1667"}
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))
DS8_UM, LETTER_MM = 18.064, HANDS[SCROLL]
LETTER_PX = LETTER_MM * 1000.0 / DS8_UM

VOID = (10, 10, 11)
ASH = (139, 139, 148)
OCHRE = (200, 151, 31)


def compose(A, B, ca, cb, m):
    """RGB: green = 59 only, magenta = 78 only, white = agreement."""
    def norm(x):
        v = x[m]
        if v.size == 0:
            return np.zeros_like(x)
        lo, hi = np.percentile(v, [2, 99.5])
        return np.clip((x - lo) / (hi - lo + 1e-9), 0, 1)
    a, b = norm(A), norm(B)
    base = 0.20 * np.maximum(a, b) * m           # faint sheet for context
    # magenta = R+B driven by the 78 keV call, green = G driven by 59 keV.
    # Where both fire all three channels light and the pixel reads white.
    g = np.clip(base + 0.95 * ca * a, 0, 1)
    mg = np.clip(base + 0.95 * cb * b, 0, 1)
    rgb = np.stack([mg, g, mg], -1)
    rgb[~m] = np.array(VOID) / 255.0
    return (rgb * 255).astype(np.uint8)


def fit(img, maxw, maxh):
    im = Image.fromarray(img)
    im.thumbnail((maxw, maxh), Image.LANCZOS)
    return im


def main():
    rep = json.load(open(os.path.join(OUT, "crossenergy.json")))["segments"]
    only = sys.argv[1] if len(sys.argv) > 1 else None
    segs = [s for s in sorted(rep) if not only or only in s]

    for seg in segs:
        f = os.path.join(OUT, f"xe_{seg}.npz")
        if not os.path.exists(f):
            continue
        d = np.load(f)
        A, B = d["A"].astype(np.float32), d["B"].astype(np.float32)
        ca, cb, m = d["ca"], d["cb"], d["m"]
        rgb = compose(A, B, ca, cb, m)

        # find the windows with the most disagreement, on shared sheet
        win = int(24 * LETTER_PX)                     # ~2160 px, ~39 mm
        dis = (cb & ~ca).astype(np.float32)
        score = ndimage.uniform_filter(dis, win // 2) * ndimage.uniform_filter(
            m.astype(np.float32), win // 2)
        picks, taken = [], np.zeros_like(score, bool)
        for _ in range(3):
            s = np.where(taken, -1, score)
            y, x = np.unravel_index(np.argmax(s), s.shape)
            if s[y, x] <= 0:
                break
            picks.append((y, x))
            y0, y1 = max(0, y - win), min(s.shape[0], y + win)
            x0, x1 = max(0, x - win), min(s.shape[1], x + win)
            taken[y0:y1, x0:x1] = True

        W = 1800
        overview = fit(rgb, W, 900)
        tiles = []
        for (y, x) in picks:
            y0 = int(np.clip(y - win // 2, 0, rgb.shape[0] - win))
            x0 = int(np.clip(x - win // 2, 0, rgb.shape[1] - win))
            tiles.append(fit(rgb[y0:y0 + win, x0:x0 + win], W // 3 - 8, 10 ** 4))

        pad, cap = 16, 34
        th = max([t.height for t in tiles], default=0)
        H = pad + overview.height + cap + (th + cap + pad if tiles else 0) + pad
        canvas = Image.new("RGB", (W + 2 * pad, H), VOID)
        dr = ImageDraw.Draw(canvas)
        canvas.paste(overview, (pad + (W - overview.width) // 2, pad))
        r = rep[seg]
        dr.text((pad, pad + overview.height + 8),
                f"PHerc1667  {seg}   GREEN 59keV only   MAGENTA 78keV only   "
                f"WHITE both   shared sheet {r['shared_sheet_pct']}%   "
                f"r={r['r_letterscale']}   consensus {r['consensus_pct']}%   "
                f"J {r['jaccard']} vs null {r['null_mean']} "
                f"= {r['enrichment']}x   p={r['p']}", fill=ASH)
        x = pad
        y = pad + overview.height + cap
        for i, t in enumerate(tiles):
            canvas.paste(t, (x, y))
            dr.text((x, y + t.height + 6),
                    f"zoom {i+1} — {win*DS8_UM/1000:.0f} mm, letter = "
                    f"{LETTER_PX:.0f} px", fill=OCHRE)
            x += t.width + 8
        p = os.path.join(OUT, f"evidence_xe_{seg}.png")
        canvas.save(p)
        print("wrote", p)


if __name__ == "__main__":
    main()
