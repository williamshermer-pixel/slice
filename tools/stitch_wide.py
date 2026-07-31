"""STITCH THE WIDE FIELD — assemble the grid and put it in front of human eyes.

The point of the wide field is that a person can judge writing where a
statistic cannot. Text has structure a 9 mm keyhole destroys: lines, columns,
margins, word spacing. So this assembles the cells into one continuous map and
renders it at a size where those things are visible, with the published calls
beside it as ground truth.

Two panels, same field, same scale:
  LEFT   our map, defogged — everything the model believes is ink
  RIGHT  the same map with the PUBLISHED calls subtracted, so what remains is
         only what nobody has called before. If there is undiscovered writing,
         it is in the right panel and it should look like LINES.

  python3 tools/stitch_wide.py
"""
import glob, json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SCROLL", "PHerc0139")
import differential_0139 as D

ROOT = D.ROOT
WIDE = os.path.join(ROOT, "out", "wide")
CH, REGION = 128, 4096
Q = REGION // 4                      # 1024 pred px per cell


def defog(p):
    g = np.clip(np.nan_to_num(p), 0, 1)
    g = g / max(g.max(), 1e-9)
    s = 1.0 / (1.0 + np.exp(-22.0 * (g - np.percentile(g, 70))))
    im = Image.fromarray((s * 255).astype(np.uint8))
    blur = im.filter(ImageFilter.GaussianBlur(6))
    a = np.asarray(im).astype(np.float32)
    return np.clip(a + 1.4 * (a - np.asarray(blur, np.float32)), 0, 255).astype(np.uint8)


def main():
    st = json.load(open(os.path.join(WIDE, "fleet.json")))
    G = st["grid"]
    cy0, cx0 = st["origin"]
    seg = st["target"]
    big = np.zeros((G * Q, G * Q), np.float32)
    tex = np.zeros((G * Q, G * Q), np.float32)
    got = 0
    for i in range(G):
        for j in range(G):
            f = os.path.join(WIDE, f"cell_{i}_{j}.npy")
            if not os.path.exists(f):
                continue
            big[i*Q:(i+1)*Q, j*Q:(j+1)*Q] = np.load(f)
            tf = os.path.join(WIDE, f"tex_{i}_{j}.npy")
            if os.path.exists(tf):
                tex[i*Q:(i+1)*Q, j*Q:(j+1)*Q] = np.load(tf)
            got += 1
    if got == 0:
        sys.exit("no cells yet")
    mm = G * REGION * 2.258 / 1000.0
    print(f"stitched {got}/{G*G} cells · {mm:.1f} mm across · {big.shape} px")

    # published calls over the same field
    t = D.TARGETS[seg]
    from PIL import Image as I
    I.MAX_IMAGE_PIXELS = None
    import io, urllib.request
    r = urllib.request.Request(f"{D.B}/{t['ink']}",
                               headers={"User-Agent": "Mozilla/5.0"})
    a = np.array(I.open(io.BytesIO(urllib.request.urlopen(r, timeout=180).read()))
                 ).astype(np.float32)
    if a.ndim == 3:
        a = a.mean(2)
    za = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{D.B}/{t['sv']}0/.zarray", headers={"User-Agent": "Mozilla/5.0"}),
        timeout=60).read().decode())
    ds = za["shape"][2] / a.shape[1]
    y0, x0 = cy0 * CH, cx0 * CH
    n = int(round(G * REGION / ds))
    iy, ix = int(round(y0 / ds)), int(round(x0 / ds))
    crop = a[iy:iy+n, ix:ix+n]
    pad = np.zeros((n, n), np.float32)
    pad[:crop.shape[0], :crop.shape[1]] = crop
    pub = np.array(I.fromarray(pad).resize(big.shape[::-1], I.BILINEAR))

    ours = defog(big)
    # what nobody has called: our confident response where published is cold
    floor = json.load(open(os.path.join(D.LB, "floor.json")))["floor"]
    new = np.where((pub < 60) & (big >= floor), big, 0.0)
    newimg = defog(new) if (new > 0).any() else np.zeros_like(ours)

    W = 900
    PAD, TOP = 22, 62
    canvas = Image.new("RGB", (2 * W + 3 * PAD, TOP + W + 96), (10, 10, 11))
    dr = ImageDraw.Draw(canvas)
    dr.text((PAD, 14), f"WIDE FIELD — {mm:.0f} mm of {seg.split('/')[-2][:30]}, "
            f"PHerc0139 (Philodemus, On Gods — unread)", fill=(233, 229, 219))
    dr.text((PAD, 34), f"{got} cells stitched · same model, same z27–89 band · "
            f"~{mm/4.32:.0f} text lines tall, ~{mm/1.61:.0f} letters across "
            f"(a single search window was 9.3 mm = 2 lines)", fill=(139, 139, 148))

    canvas.paste(Image.fromarray(ours).resize((W, W)).convert("RGB"), (PAD, TOP))
    dr.text((PAD + 4, TOP + W + 8),
            "OUR MAP — everything the model calls ink", fill=(139, 139, 148))

    rgb = np.stack([np.asarray(Image.fromarray(tex.astype(np.uint8)))] * 3, -1)
    lo, hi = np.percentile(tex, 2), np.percentile(tex, 99)
    g = np.clip((tex - lo) / max(hi - lo, 1e-6) * 150, 0, 150).astype(np.uint8)
    rgb = np.stack([g] * 3, -1)
    hot = newimg > 120
    rgb[hot] = [255, 180, 40]
    canvas.paste(Image.fromarray(rgb).resize((W, W)).convert("RGB"),
                 (PAD * 2 + W, TOP))
    dr.text((PAD * 2 + W + 4, TOP + W + 8),
            "UNCALLED ONLY — ochre is ink nobody has called, on the papyrus. "
            "Writing would appear as LINES.", fill=(139, 139, 148))
    dr.text((PAD, TOP + W + 34),
            f"floor {floor:.3f} @ 0.2% blank FPR · uncalled hot pixels: "
            f"{int(hot.sum())} ({100*hot.mean():.3f}% of field) · "
            f"line pitch would be {4.32:.2f} mm = {4.32/mm*W:.0f} px here",
            fill=(200, 160, 120))
    dr.text((PAD, TOP + W + 54),
            "Statistics rank; eyes decide. Look for parallel bands at the line "
            "pitch — damage has no periodicity.", fill=(139, 139, 148))

    out = os.path.join(ROOT, "out", "wide_field.png")
    canvas.save(out)
    np.save(os.path.join(WIDE, "stitched.npy"), big)
    print(f"uncalled hot pixels: {int(hot.sum())} ({100*hot.mean():.3f}%)")
    print(f"-> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
