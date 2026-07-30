"""FLEET SWEEP — grade every fleet map under the lost-book scribe's OWN hand
(measured 2026-07-29: letters median 1.09 mm, line pitch 4.57 mm). Gallery
of the top windows across all segments for William's eyes.

Usage: python3 fleet_sweep.py <dir-with-pred_*.npy-and-meta_*.json>
"""
import os, sys, json, glob
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "out", "fleet")
UM = 9.03
WIN, STR = 330, 110
ADV = int(round(0.70 * 1000 / UM))          # his letter advance ~0.70 mm

cands = []
for pf in sorted(glob.glob(os.path.join(DIR, "pred_*.npy"))):
    i = pf.split("_")[-1].split(".")[0]
    meta = json.load(open(os.path.join(DIR, f"meta_{i}.json")))
    pred = np.load(pf)
    q = np.percentile(pred, [90, 97, 99])
    faint = (pred > q[0]) & (pred < q[1])
    called = pred > q[2]
    H, W = pred.shape
    for y in range(0, H - WIN + 1, STR):
        for x in range(0, W - WIN + 1, STR):
            fw = faint[y:y+WIN, x:x+WIN]
            if called[y:y+WIN, x:x+WIN].mean() > 0.03:
                continue
            if not (0.02 < fw.mean() < 0.40):
                continue
            lab, n = ndimage.label(fw)
            good = []
            for j in range(1, n + 1):
                ys, xs = np.where(lab == j)
                h = (ys.max()-ys.min()+1)*UM/1000
                w = (xs.max()-xs.min()+1)*UM/1000
                if 0.7 < h < 2.2 and 0.4 < w < 3.0 and len(ys) > 40:
                    good.append((ys, xs))
            if not (3 <= len(good) <= 20):
                continue
            colp = fw.sum(0).astype(float); colp -= colp.mean()
            if colp.std() < 1e-6:
                continue
            ac = np.correlate(colp, colp, "full")[WIN-1:]
            ac /= ac[0] + 1e-9
            r = float(ac[int(ADV*0.7):int(ADV*1.3)].max())
            score = len(good) * max(r, 0)
            if score > 0.8:
                cands.append((score, len(good), r, meta["seg"], pred, y, x, good))
cands.sort(key=lambda c: -c[0])
print(f"{len(cands)} windows cleared across the fleet")

S = 500
panels = []
for score, ng, r, seg, pred, y, x, good in cands[:9]:
    crop = pred[y:y+WIN, x:x+WIN]
    lo, hi = np.percentile(crop, [2, 99.5])
    g = (np.clip((crop-lo)/max(hi-lo, 1e-9), 0, 1)*255).astype(np.uint8)
    img = Image.fromarray(g).resize((S, S), Image.LANCZOS).convert("RGB")
    d = ImageDraw.Draw(img)
    f = S / WIN
    for ys, xs in good:
        d.rectangle([xs.min()*f, ys.min()*f, xs.max()*f, ys.max()*f],
                    outline=(80, 220, 120), width=2)
    bar = int(1.09*1000/UM*f)
    d.line([(16, S-24), (16+bar, S-24)], fill=(255, 200, 40), width=4)
    d.text((16, S-46), "1.1mm = his letter", fill=(255, 200, 40))
    d.text((6, 6), f"{seg.split('/')[-2][:22]}  {ng} whispers r{r:+.2f}",
           fill=(255, 200, 40))
    panels.append(np.array(img))
if panels:
    while len(panels) % 3:
        panels.append(np.zeros_like(panels[0]))
    rows = [np.concatenate(panels[k:k+3], 1) for k in range(0, len(panels), 3)]
    out_p = os.path.join(os.path.dirname(DIR.rstrip("/")), "fleet_gallery.png")
    Image.fromarray(np.concatenate(rows, 0)).save(out_p)
    print(f"GALLERY: {out_p}")
else:
    print("fleet verdict: clean silence under his hand, all segments")
