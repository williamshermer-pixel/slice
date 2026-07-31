"""RENDER THE 3D — make the depth claim visible to human eyes.

William's standing rule: every finding ships as a render before it is
believed. The claim under scrutiny is that these labels are genuinely
depth-resolved rather than one image copied down the stack, so the figure is
built to expose that directly — and would look obviously wrong if v1's
projected labels were passed to it.

  A  the papyrus, depth-averaged
  B  the ink label COLOURED BY DEPTH — a projection would be one flat colour
  C  an XZ cross-section: the sheet in grey, ink riding it, both drifting in z
  D  the depth histogram of every labelled ink voxel

  python3 tools/render_3d.py [pair_dir]
"""
import json, os, sys, zlib
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK = (233, 229, 219)
DIM = (139, 139, 148)
OCHRE = (200, 151, 31)
VOID = (10, 10, 11)


def read(d, arr):
    za = json.loads(open(os.path.join(d, arr, ".zarray")).read())
    raw = zlib.decompress(open(os.path.join(d, arr, "0.0.0"), "rb").read())
    return np.frombuffer(raw, np.uint8).reshape(za["chunks"])


def depth_ramp(t):
    """Shallow -> deep. Cool slate through papyrus to hot ochre, so depth
    reads as a physical gradient rather than a rainbow."""
    t = np.clip(t, 0, 1)[..., None]
    c0 = np.array([70, 96, 130], np.float32)      # shallow
    c1 = np.array([233, 229, 219], np.float32)    # mid
    c2 = np.array([200, 151, 31], np.float32)     # deep
    lo = c0 + (c1 - c0) * (t / 0.5)
    hi = c1 + (c2 - c1) * ((t - 0.5) / 0.5)
    return np.where(t < 0.5, lo, hi).astype(np.uint8)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else None
    if not d:
        man = json.load(open(os.path.join(ROOT, "out", "pairs", "MANIFEST.json")))
        best = max((p for p in man["pairs"] if p["kind"] == "ink"),
                   key=lambda p: p["ink_columns"])
        d = os.path.join(ROOT, "out", "pairs", best["scroll"], best["pair"])
    at = json.loads(open(os.path.join(d, "label", ".zattrs")).read())
    img, lab = read(d, "image"), read(d, "label")
    D, H, W = lab.shape
    ink = lab == 1

    # ---- per-pixel ink depth
    zz = np.arange(D)[:, None, None]
    n = ink.sum(0)
    has = n > 0
    cen = np.where(has, (ink * zz).sum(0) / np.maximum(n, 1), np.nan)
    v = cen[has]
    zlo, zhi = np.percentile(v, 2), np.percentile(v, 98)
    print(f"{os.path.basename(d)}")
    print(f"  ink columns {int(has.sum())} · depth {v.min():.0f}–{v.max():.0f} "
          f"(sd {v.std():.2f}) · {len(set(np.round(v).astype(int).tolist()))} centres")

    S = 460
    PAD, TOP = 24, 58
    img_w = 2 * S + 3 * PAD
    xz_h = 250
    canvas = Image.new("RGB", (img_w, TOP + S + 34 + xz_h + 34 + 120), VOID)
    dr = ImageDraw.Draw(canvas)
    dr.text((PAD, 14), "TRUE 3D INK LABEL — depth is measured, not projected",
            fill=INK)
    dr.text((PAD, 32), f"{at['scroll']} · {at['segment'].split('/')[-2][:34]} · "
            f"{at['crop_px']}³ crop · villa #192", fill=DIM)

    # ---- A: papyrus
    band = img[27:89].mean(0)
    lo, hi = np.percentile(band, 2), np.percentile(band, 99)
    pap = np.clip((band - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
    canvas.paste(Image.fromarray(pap).resize((S, S)).convert("RGB"), (PAD, TOP))
    dr.text((PAD + 4, TOP + S + 6), "A  the papyrus (depth-averaged)", fill=DIM)

    # ---- B: ink coloured by depth
    t = (cen - zlo) / max(zhi - zlo, 1e-6)
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[:] = (24, 24, 27)
    rgb[has] = depth_ramp(np.nan_to_num(t))[has]
    x2 = PAD * 2 + S
    canvas.paste(Image.fromarray(rgb).resize((S, S), Image.NEAREST), (x2, TOP))
    dr.text((x2 + 4, TOP + S + 6),
            "B  ink, COLOURED BY DEPTH — a projection would be one flat colour",
            fill=DIM)
    # depth key
    kx, ky, kw = x2 + S - 150, TOP + 10, 130
    for i in range(kw):
        c = tuple(int(x) for x in depth_ramp(np.array([i / kw]))[0])
        dr.line([kx + i, ky, kx + i, ky + 7], fill=c)
    dr.text((kx - 4, ky + 10), f"layer {zlo:.0f}", fill=DIM)
    dr.text((kx + kw - 34, ky + 10), f"{zhi:.0f}", fill=DIM)

    # ---- C: XZ cross-section, the row with the most ink
    row = int(np.argmax(ink.sum(axis=(0, 2))))
    sheet = img[:, row, :].astype(np.float32)
    lo, hi = np.percentile(sheet, 2), np.percentile(sheet, 99)
    xz = np.clip((sheet - lo) / max(hi - lo, 1e-6) * 200, 0, 200).astype(np.uint8)
    xzc = np.stack([xz] * 3, -1)
    m = ink[:, row, :]
    xzc[m] = OCHRE
    y3 = TOP + S + 34
    canvas.paste(Image.fromarray(xzc).resize((img_w - 2 * PAD, xz_h),
                                             Image.NEAREST), (PAD, y3))
    dr.text((PAD + 4, y3 + xz_h + 6),
            f"C  XZ slice at row {row} — depth runs vertically. Grey is the "
            f"sheet; ochre is labelled ink, riding it as it drifts in z.",
            fill=DIM)

    # ---- D: depth histogram
    y4 = y3 + xz_h + 34
    hist, edges = np.histogram(v, bins=48)
    hw = img_w - 2 * PAD
    hh = 60
    hist = hist / max(hist.max(), 1)
    for i, hv in enumerate(hist):
        bx = PAD + int(i * hw / len(hist))
        bh = int(hv * hh)
        if bh:
            dr.rectangle([bx, y4 + hh - bh, bx + max(1, hw // len(hist) - 1),
                          y4 + hh], fill=OCHRE)
    dr.text((PAD, y4 + hh + 6),
            f"D  depth of every labelled ink voxel — spread across "
            f"{len(set(np.round(v).astype(int).tolist()))} distinct centres, "
            f"sd {v.std():.1f} layers. One spike would mean a projection.",
            fill=DIM)
    dr.text((PAD, y4 + hh + 24),
            f"floor {at['floor']:.3f} @ {100*at['floor_blank_fpr']:.1f}% blank FPR · "
            f"condition-control AUC {at['condition_control_auc']:.3f} "
            f"(ink vs same-preservation blank sheet) · "
            f"depth resolution ±{at.get('depth_resolution_layers', 10)//2} layers",
            fill=(200, 160, 120))

    out = os.path.join(ROOT, "out", "true3d.png")
    canvas.save(out)
    print(f"-> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
