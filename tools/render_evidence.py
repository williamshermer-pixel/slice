"""EVIDENCE RENDER — the cityscape. Human eyes on the aimed-window finding.

Three panels per segment, same window: published ink map | weave_fill
feature | exaggerated-relief hillshade of the height field (the cityscape —
tall buildings and small buildings). Exaggeration is display-only: it cannot
create signal, it lets a human judge the signal that scored.
"""
import os, sys, json
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("INK_TAG", "4")
import pack as P
import native as N

_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import dogs as D
finally:
    sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUTP = os.path.join(HERE, "..", "out", "evidence_cityscape.png")


def norm(a):
    lo, hi = np.percentile(a, [2, 98])
    return np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)


def hillshade(h, exagg=8.0, az=315.0, alt=45.0):
    gy, gx = np.gradient(h.astype(np.float32) * exagg)
    a, l = np.radians(az), np.radians(alt)
    lx, ly, lz = np.sin(a) * np.cos(l), np.cos(a) * np.cos(l), np.sin(l)
    nz = 1.0 / np.sqrt(gx**2 + gy**2 + 1)
    return np.clip((-gx * nz * lx - gy * nz * ly + nz * lz), 0, 1)


d = json.load(open(os.path.join(HERE, "..", "findings", "native_rerun2.json")))
rows = sorted(d["detail"]["weave_fill"]["native"], key=lambda r: -r["excess"])
segs, want = [], 3
for r in rows:
    base = r["seg"].rsplit("@", 1)[0]
    if base not in [s[0] for s in segs]:
        segs.append((base, r["excess"]))
    if len(segs) >= want:
        break

pairs = {t_l1["seg"].rsplit("@", 1)[0]: t_nat for t_l1, t_nat in N.discover()}
panels_all = []
for base, exc in segs:
    t_nat = pairs.get(base)
    if t_nat is None:
        continue
    tile = P.load_tile(t_nat)
    if tile is None:
        continue
    rng = np.random.default_rng(1000)
    V = D.sample_variant(rng)
    V["features"], V["weights"] = ["weave_fill"], [1.0]
    fm = D.feature_map(tile, V)
    if fm is None:
        continue
    h = P.height_map(tile)
    if isinstance(h, tuple):
        h = h[0]
    H, W = fm.shape
    ds = tile["ds"]
    ink = tile["ink"][tile["iy"]:tile["iy"] + int(H / ds),
                      tile["ix"]:tile["ix"] + int(W / ds)]
    ink_up = np.array(Image.fromarray(
        (norm(ink) * 255).astype(np.uint8)).resize((W, H), Image.NEAREST))
    p1 = ink_up
    p2 = (norm(fm) * 255).astype(np.uint8)
    p3 = (hillshade(h) * 255).astype(np.uint8)
    strip = np.concatenate([p1, np.full((H, 4), 255, np.uint8), p2,
                            np.full((H, 4), 255, np.uint8), p3], axis=1)
    img = Image.fromarray(strip).convert("RGB")
    dr = ImageDraw.Draw(img)
    dr.text((6, 6), f"{tile['scroll']}  excess +{exc:.2f}", fill=(255, 200, 40))
    dr.text((6, H - 16), "published ink", fill=(255, 200, 40))
    dr.text((W + 10, H - 16), "weave_fill (scored)", fill=(255, 200, 40))
    dr.text((2 * W + 14, H - 16), "cityscape relief x8", fill=(255, 200, 40))
    panels_all.append(np.array(img))
    print(f"rendered {tile['scroll']} {base[-24:]} excess +{exc:.2f}", flush=True)

if panels_all:
    w = max(p.shape[1] for p in panels_all)
    padded = [np.pad(p, ((0, 0), (0, w - p.shape[1]), (0, 0))) for p in panels_all]
    gap = np.full((6, w, 3), 255, np.uint8)
    out = np.concatenate(sum(([p, gap] for p in padded), [])[:-1], axis=0)
    Image.fromarray(out).save(OUTP)
    print(f"written: {OUTP}")
else:
    print("nothing rendered")
