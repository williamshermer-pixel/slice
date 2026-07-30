"""REGEN LETTER — the money shot. A known-letter window of the GP segment,
rendered three ways: published ink map | published 2.258 um surface render |
OUR regenerated native 1.129 um surface. Window chosen inside the scanned
half of the native volume, at mixed ink coverage (strokes AND gaps).

Correspondences (all verified tonight): mesh grid step = 20 level-0 native
voxels; L1 canvas = grid x 10; ink jpg = canvas / 8 = grid x 1.25.
Mesh coords are AS-PUBLISHED (scale 1, x->axis2, y->axis1, z->axis0).
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
import numpy as np
import tifffile
from PIL import Image, ImageDraw

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOL = "PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr/0"
SV = ("PHercParis4/segments/20230702185753/surface-volumes/"
      "1.129um-0.23m-78keV-volume-20260608103018-L1.zarr")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")
CH = 128
N = 96          # mesh gridpoints per side (~2.2 mm)
UP = 20         # upsample factor -> 768x768 samples, ~2.8 um/px effective


def get(u, t=90):
    return urllib.request.urlopen(u, timeout=t).read()


def bil_up(a, F):
    im = Image.fromarray(a.astype(np.float32), mode="F")
    return np.array(im.resize((a.shape[1]*F, a.shape[0]*F), Image.BILINEAR))


def main():
    import sys
    tgt = json.load(open(os.path.join(HERE, "..", "findings", "targets.json")))
    t = [x for x in tgt if "20230702185753" in x["seg"]][0]
    ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
    if ink.ndim == 3:
        ink = ink.mean(2)
    za = json.loads(get(f"{B}/{VOL}/.zarray").decode())
    D0, D1, D2 = za["shape"]
    X = tifffile.imread(os.path.join(OUT, "mesh_x.tif"))
    Y = tifffile.imread(os.path.join(OUT, "mesh_y.tif"))
    Z = tifffile.imread(os.path.join(OUT, "mesh_z.tif"))
    gh, gw = X.shape
    inv = (Z > 60) & (Z < D0-60) & (Y > 60) & (Y < D1-60) & (X > 60) & (X < D2-60)
    # ink coverage at grid scale: ink px = grid * 1.25
    gy = np.clip((np.arange(gh) * 1.25).astype(int), 0, ink.shape[0]-1)
    gx = np.clip((np.arange(gw) * 1.25).astype(int), 0, ink.shape[1]-1)
    inkg = (ink[np.ix_(gy, gx)] > 128).astype(np.float32)
    best, bscore = None, -1
    for r in range(0, gh-N, 24):
        for c in range(0, gw-N, 24):
            if not inv[r:r+N, c:c+N].all():
                continue
            cov = inkg[r:r+N, c:c+N].mean()
            s = -abs(cov - 0.35)
            if s > bscore:
                bscore, best = s, (r, c, cov)
    if best is None:
        print("no window"); return
    r0, c0, cov = best
    print(f"window ({r0},{c0}) ink coverage {cov:.2f}", flush=True)

    # upsampled mesh coords + normals
    P = np.stack([bil_up(Z[r0:r0+N, c0:c0+N], UP),
                  bil_up(Y[r0:r0+N, c0:c0+N], UP),
                  bil_up(X[r0:r0+N, c0:c0+N], UP)])
    du = np.gradient(P, axis=2); dv = np.gradient(P, axis=1)
    nrm = np.cross(du.reshape(3, -1).T, dv.reshape(3, -1).T).T.reshape(P.shape)
    nrm /= (np.linalg.norm(nrm, axis=0, keepdims=True) + 1e-9)
    M = N * UP

    cache = {}
    def chunk(cz, cy, cx):
        k = (cz, cy, cx)
        if k not in cache:
            try:
                b = get(f"{B}/{VOL}/{cz}/{cy}/{cx}")
                cache[k] = (np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                            if len(b) == CH**3 else None)
            except Exception:
                cache[k] = None
        return cache[k]

    OFFS = [-8, -4, 0, 4, 8]
    stack = np.zeros((len(OFFS), M, M), np.uint8)
    t0 = time.time()
    for li, off in enumerate(OFFS):
        S = np.rint(P + nrm*off).astype(np.int64)
        S[0] = S[0].clip(0, D0-1); S[1] = S[1].clip(0, D1-1); S[2] = S[2].clip(0, D2-1)
        ck0, ck1, ck2 = S[0]//CH, S[1]//CH, S[2]//CH
        keys = set(zip(ck0.ravel().tolist(), ck1.ravel().tolist(), ck2.ravel().tolist()))
        with cf.ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(lambda k: chunk(*k), [k for k in keys if k not in cache]))
        flat = np.zeros(M*M, np.uint8)
        c0f, c1f, c2f = ck0.ravel(), ck1.ravel(), ck2.ravel()
        s0, s1, s2 = (S[0] % CH).ravel(), (S[1] % CH).ravel(), (S[2] % CH).ravel()
        for k, arr in cache.items():
            if arr is None:
                continue
            m = (c0f == k[0]) & (c1f == k[1]) & (c2f == k[2])
            if m.any():
                flat[m] = arr[s0[m], s1[m], s2[m]]
        stack[li] = flat.reshape(M, M)
        print(f"  native layer {off:+d}: mean {stack[li].mean():.0f} "
              f"chunks {len(cache)} {time.time()-t0:.0f}s", flush=True)
    native = stack.max(0)          # crackle sits proud: max across the band

    # published L1 surface render, same window (canvas = grid x 10)
    zs = json.loads(get(f"{B}/{SV}/0/.zarray").decode())
    Dv = zs["shape"][0]
    y0c, x0c = r0*10, c0*10
    Wc = N*10
    L1 = np.zeros((Wc, Wc), np.float32)
    cnt = np.zeros((Wc, Wc), np.float32)
    def gs(cy, cx):
        try:
            b = get(f"{B}/{SV}/0/0/{cy}/{cx}")
            if len(b) == Dv*CH*CH:
                a = np.frombuffer(b, np.uint8).reshape(Dv, CH, CH)
                mb = a[Dv//2-6:Dv//2+6].max(0).astype(np.float32)
                ys, xs = cy*CH - y0c, cx*CH - x0c
                yA, xA = max(0, ys), max(0, xs)
                yB, xB = min(Wc, ys+CH), min(Wc, xs+CH)
                if yB > yA and xB > xA:
                    L1[yA:yB, xA:xB] = mb[yA-ys:yB-ys, xA-xs:xB-xs]
                    cnt[yA:yB, xA:xB] = 1
        except Exception:
            pass
    keys = [(a, b_) for a in range(y0c//CH, (y0c+Wc)//CH + 1)
            for b_ in range(x0c//CH, (x0c+Wc)//CH + 1)]
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        list(ex.map(lambda k: gs(*k), keys))
    print(f"L1 window {(cnt>0).mean()*100:.0f}% filled", flush=True)

    # ink map crop (ink px = grid x 1.25)
    ic = ink[int(r0*1.25):int((r0+N)*1.25), int(c0*1.25):int((c0+N)*1.25)]

    def norm8(a):
        v = a[a > 0]
        lo, hi = (np.percentile(v, [2, 98]) if v.size else (0, 255))
        return (np.clip((a.astype(np.float32)-lo)/max(hi-lo, 1), 0, 1)*255).astype(np.uint8)
    SIDE = 768
    p1 = np.array(Image.fromarray(norm8(ic)).resize((SIDE, SIDE), Image.LANCZOS))
    p2 = np.array(Image.fromarray(norm8(L1)).resize((SIDE, SIDE), Image.LANCZOS))
    p3 = np.array(Image.fromarray(norm8(native)).resize((SIDE, SIDE), Image.LANCZOS))
    gap = np.full((SIDE, 4), 255, np.uint8)
    strip = np.concatenate([p1, gap, p2, gap, p3], 1)
    img = Image.fromarray(strip).convert("RGB")
    d = ImageDraw.Draw(img)
    d.text((8, 8), "published ink map", fill=(255, 200, 40))
    d.text((SIDE+12, 8), "published 2.258um render", fill=(255, 200, 40))
    d.text((2*SIDE+16, 8), "OUR native 1.129um regeneration", fill=(80, 220, 120))
    d.text((8, SIDE-22), f"GP segment, 2.2mm window, ink cov {cov:.2f}",
           fill=(200, 200, 205))
    img.save(os.path.join(OUT, "money_shot_v2.png"))
    print("MONEY SHOT written: out/money_shot_v2.png", flush=True)


if __name__ == "__main__":
    main()
