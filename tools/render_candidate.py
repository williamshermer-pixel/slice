#!/usr/bin/env python3
"""Evidence render for a cross-energy conjunction candidate — the arbiter.

Law 8: statistics gate, human eyes verify. In this project the render has
killed a fully-controlled false positive twice in one night, including one that
had cleared spatial nulls, independent replication AND a physics control. A
p-value says a spot is unusual; only looking says whether it is a LETTER.

Four panels across, all the same crop, all at the same stretch:

    1  59 keV map          what the newer published detector sees here
    2  78 keV map          what the older independent scan sees here
    3  min(z59, z78)       the conjunction statistic that fired
    4  context             the same crop with published calls overlaid
                           (green 59, magenta 78) so you can see whether the
                           candidate sits in a text block or out on blank sheet

What to ask of it, in order:
  - Is there letter-SHAPED mass, or a smooth blob? Condition is smooth.
  - Does it sit on a text BASELINE, in line with called letters either side?
  - Is it at the sheet edge, a crack, or a mask boundary? Those are geometry.
  - Do BOTH energy panels show it independently, or is one carrying it?

    SCROLL=PHerc0139 python3 tools/render_candidate.py 20260311000000
"""
import os, sys, json
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc0139")
_DIRS = {"PHerc1667": "s1667"}
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))
DS8_UM = 18.064
LETTER_PX = HANDS[SCROLL] * 1000.0 / DS8_UM

VOID, ASH, OCHRE = (10, 10, 11), (139, 139, 148), (200, 151, 31)


def stretch(a, m):
    v = a[m] if m is not None and m.any() else a
    lo, hi = np.percentile(v, [2, 99.5])
    return np.clip((a - lo) / (hi - lo + 1e-9), 0, 1)


def main():
    seg = sys.argv[1]
    halo = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0   # in letters

    xe = np.load(os.path.join(OUT, f"xe_{seg}.npz"))
    cj = np.load(os.path.join(OUT, f"cj_{seg}.npz"))
    rep = json.load(open(os.path.join(OUT, "conjunction.json")))["segments"][seg]
    if not rep["survivors"]:
        print(f"{seg}: no survivors to render")
        return

    A = xe["A"].astype(np.float32)
    B = xe["B"].astype(np.float32)
    m, ca, cb = xe["m"], xe["ca"], xe["cb"]
    J = cj["J"].astype(np.float32)

    win = int(round(halo * LETTER_PX))
    for n, s in enumerate(rep["survivors"], 1):
        y, x = s["y"], s["x"]
        y0 = int(np.clip(y - win // 2, 0, max(0, A.shape[0] - win)))
        x0 = int(np.clip(x - win // 2, 0, max(0, A.shape[1] - win)))
        sl = (slice(y0, y0 + win), slice(x0, x0 + win))
        mm = m[sl]
        a, b = stretch(A[sl], mm), stretch(B[sl], mm)
        j = J[sl]
        jj = np.clip((j - np.percentile(j, 5)) /
                     (np.percentile(j, 99.9) - np.percentile(j, 5) + 1e-9), 0, 1)

        ctx = np.stack([np.clip(0.35 * np.maximum(a, b) + 0.9 * cb[sl] * b, 0, 1),
                        np.clip(0.35 * np.maximum(a, b) + 0.9 * ca[sl] * a, 0, 1),
                        np.clip(0.35 * np.maximum(a, b) + 0.9 * cb[sl] * b, 0, 1)],
                       -1)
        ctx[~mm] = np.array(VOID) / 255.0

        panels = [np.stack([a] * 3, -1), np.stack([b] * 3, -1),
                  np.stack([jj] * 3, -1), ctx]
        # crosshair on the candidate, drawn as a gap-centre reticle so the
        # marker never covers the thing being judged
        cy, cx = y - y0, x - x0
        for p in panels:
            r1, r2 = int(1.2 * LETTER_PX), int(2.0 * LETTER_PX)
            for d in range(r1, r2):
                for (yy, xx) in ((cy - d, cx), (cy + d, cx),
                                 (cy, cx - d), (cy, cx + d)):
                    if 0 <= yy < win and 0 <= xx < win:
                        p[yy, xx] = np.array(OCHRE) / 255.0

        side = 620
        ims = [Image.fromarray((p * 255).astype(np.uint8)).resize(
            (side, side), Image.LANCZOS) for p in panels]
        pad, cap, top = 14, 30, 40
        W = 4 * side + 5 * pad
        canvas = Image.new("RGB", (W, top + side + cap + pad), VOID)
        dr = ImageDraw.Draw(canvas)
        dr.text((pad, 12),
                f"{SCROLL}  {seg}  candidate {n}/{len(rep['survivors'])}   "
                f"min-z {s['z']}  vs null mean {rep['null_top_mean']} "
                f"(p95 {rep['null_top_p95']})  p={rep['p']}   "
                f"crop {win*DS8_UM/1000:.1f} mm, letter {LETTER_PX:.0f} px   "
                f"at {s['mm_x']}, {s['mm_y']} mm", fill=ASH)
        labels = ["59 keV map", "78 keV map (independent scan)",
                  "min(z59, z78) — the statistic", "published calls: G=59 M=78"]
        for i, (im, lab) in enumerate(zip(ims, labels)):
            xo = pad + i * (side + pad)
            canvas.paste(im, (xo, top))
            dr.text((xo, top + side + 8), lab, fill=OCHRE)
        p = os.path.join(OUT, f"cand_{seg}_{n}.png")
        canvas.save(p)
        print("wrote", p)


if __name__ == "__main__":
    main()
