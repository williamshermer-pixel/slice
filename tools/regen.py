"""REGEN v0 — regenerate native-resolution surface patches for Scroll 1.

The play (science-deep-dive Part II-D): Scroll 1's surface volumes are only
published at 2.258 um; the field documents legibility dying between 1.1 and
2.4 um; the native 1.129 um raw volume AND per-segment meshes are public.
Nobody has resampled the mesh against the native raw. This tool does.

v0 = proof of life on one patch of the GP banner segment: sample the native
volume at mesh points, +/- offsets along the surface normal, render layers.
Coordinate mapping (verified empirically before believing): mesh tif values
are in HALF-native-voxel units (filename says 1.129 um, ranges say 0.5645 —
the project's third filename lie); mapping z->axis0, y->axis1, x->axis2
after halving fits all three axes.
"""
import os, sys, json, time, urllib.request
import concurrent.futures as cf
import numpy as np
import tifffile

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOL = "PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr/0"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
MESH = os.path.join(OUT, "mesh_%s.tif")
N = 192              # mesh points per side (~2.2 mm)
OFFS = list(range(-24, 25, 4))   # 13 layers along the normal, native voxels

def get(u, t=90):
    return urllib.request.urlopen(u, timeout=t).read()

def main():
    za = json.loads(get(f"{B}/{VOL}/.zarray").decode())
    D0, D1, D2 = za["shape"]
    X = tifffile.imread(MESH % "x") / 2.0
    Y = tifffile.imread(MESH % "y") / 2.0
    Z = tifffile.imread(MESH % "z") / 2.0
    H, W = X.shape
    # find a fully-valid window near the middle
    valid = (X > 0)
    cy, cx = H // 2, W // 2
    for r in range(0, 2000, 50):
        ok = False
        for dy in (-r, 0, r):
            for dx in (-r, 0, r):
                y0, x0 = cy + dy, cx + dx
                if 0 <= y0 and y0 + N < H and 0 <= x0 and x0 + N < W and \
                   valid[y0:y0+N, x0:x0+N].all():
                    ok = True; break
            if ok: break
        if ok: break
    if not ok:
        print("no fully-valid window found"); return
    print(f"mesh window ({y0},{x0}) size {N}x{N}", flush=True)
    # Axis mapping: z->axis0 is forced by ranges; the y/x assignment to
    # axes 1/2 was ambiguous. First guess (Y->1, X->2) rendered edge-on
    # windings — the slicing-across-sheets signature. Swapped is correct.
    P = np.stack([Z[y0:y0+N, x0:x0+N], X[y0:y0+N, x0:x0+N],
                  Y[y0:y0+N, x0:x0+N]])            # (3, N, N) in native vox
    # normals from tangents (grid spacing is uniform; direction is all we need)
    du = np.gradient(P, axis=2); dv = np.gradient(P, axis=1)
    nrm = np.cross(du.reshape(3, -1).T, dv.reshape(3, -1).T).T.reshape(3, N, N)
    nrm /= (np.linalg.norm(nrm, axis=0, keepdims=True) + 1e-9)

    CH = 128
    cache = {}
    def chunk(cz, cyy, cxx):
        k = (cz, cyy, cxx)
        if k not in cache:
            try:
                b = get(f"{B}/{VOL}/{cz}/{cyy}/{cxx}")
                cache[k] = (np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                            if len(b) == CH**3 else None)
            except Exception:
                cache[k] = None
        return cache[k]

    stack = np.zeros((len(OFFS), N, N), np.uint8)
    t0 = time.time()
    for li, off in enumerate(OFFS):
        S = np.rint(P + nrm * off).astype(np.int64)   # (3,N,N)
        S[0] = S[0].clip(0, D0 - 1); S[1] = S[1].clip(0, D1 - 1)
        S[2] = S[2].clip(0, D2 - 1)
        ck = (S[0] // CH, S[1] // CH, S[2] // CH)
        keys = set(zip(ck[0].ravel().tolist(), ck[1].ravel().tolist(),
                       ck[2].ravel().tolist()))
        with cf.ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(lambda k: chunk(*k), [k for k in keys if k not in cache]))
        out = np.zeros((N, N), np.uint8)
        for j in range(N):
            for i in range(N):
                c = cache.get((int(ck[0][j, i]), int(ck[1][j, i]), int(ck[2][j, i])))
                if c is not None:
                    out[j, i] = c[int(S[0][j, i] % CH), int(S[1][j, i] % CH),
                                  int(S[2][j, i] % CH)]
        stack[li] = out
        nz = (out > 0).mean()
        print(f"  layer {off:+3d}: nonzero {nz*100:.0f}%  mean {out.mean():.0f}  "
              f"chunks so far {len(cache)}  {time.time()-t0:.0f}s", flush=True)

    np.save(os.path.join(OUT, "regen_patch.npy"), stack)
    from PIL import Image
    best = max(range(len(OFFS)), key=lambda i: stack[i].std())
    strip = np.concatenate([stack[len(OFFS)//2], np.full((N, 3), 255, np.uint8),
                            stack[best]], axis=1)
    lo, hi = np.percentile(strip[strip > 0], [2, 98]) if (strip > 0).any() else (0, 255)
    img = ((np.clip((strip.astype(np.float32) - lo) / max(hi - lo, 1), 0, 1)) * 255).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1]*3, img.shape[0]*3),
                                Image.LANCZOS).save(os.path.join(OUT, "regen_proof.png"))
    print(f"PROOF written: out/regen_proof.png (mid layer | best-contrast layer)")

if __name__ == "__main__":
    main()
