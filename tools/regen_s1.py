import os, sys, json, time, urllib.request
import concurrent.futures as cf
import numpy as np
import tifffile

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOL = "PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr/0"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
CH = 128
za = json.loads(urllib.request.urlopen(f"{B}/{VOL}/.zarray", timeout=60).read().decode())
D0, D1, D2 = za["shape"]
X = tifffile.imread(os.path.join(OUT, "mesh_x.tif"))
Y = tifffile.imread(os.path.join(OUT, "mesh_y.tif"))
Z = tifffile.imread(os.path.join(OUT, "mesh_z.tif"))
H, W = X.shape
inv = (Z > 40) & (Z < D0-40) & (Y > 40) & (Y < D1-40) & (X > 40) & (X < D2-40)
print(f"grid {X.shape}, in-volume fraction at s=1: {inv.mean()*100:.1f}%", flush=True)
N = 192
best = None
for r in range(0, H-N, 64):
    for c in range(0, W-N, 64):
        if inv[r:r+N, c:c+N].all():
            best = (r, c); break
    if best: break
if not best:
    print("no fully in-volume window"); raise SystemExit
r0, c0 = best
print(f"window ({r0},{c0})", flush=True)
P = np.stack([Z[r0:r0+N, c0:c0+N], Y[r0:r0+N, c0:c0+N], X[r0:r0+N, c0:c0+N]])
du = np.gradient(P, axis=2); dv = np.gradient(P, axis=1)
nrm = np.cross(du.reshape(3,-1).T, dv.reshape(3,-1).T).T.reshape(3, N, N)
nrm /= (np.linalg.norm(nrm, axis=0, keepdims=True) + 1e-9)
cache = {}
def chunk(cz, cy, cx):
    k = (cz, cy, cx)
    if k not in cache:
        try:
            b = urllib.request.urlopen(f"{B}/{VOL}/{cz}/{cy}/{cx}", timeout=60).read()
            cache[k] = (np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                        if len(b) == CH**3 else None)
        except Exception:
            cache[k] = None
    return cache[k]
OFFS = [-16, -8, 0, 8, 16]
stack = np.zeros((len(OFFS), N, N), np.uint8)
t0 = time.time()
for li, off in enumerate(OFFS):
    S = np.rint(P + nrm*off).astype(np.int64)
    S[0] = S[0].clip(0, D0-1); S[1] = S[1].clip(0, D1-1); S[2] = S[2].clip(0, D2-1)
    ck = (S[0]//CH, S[1]//CH, S[2]//CH)
    keys = set(zip(ck[0].ravel().tolist(), ck[1].ravel().tolist(), ck[2].ravel().tolist()))
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(lambda k: chunk(*k), [k for k in keys if k not in cache]))
    out = np.zeros((N, N), np.uint8)
    for j in range(N):
        for i in range(N):
            cc = cache.get((int(ck[0][j,i]), int(ck[1][j,i]), int(ck[2][j,i])))
            if cc is not None:
                out[j,i] = cc[int(S[0][j,i]%CH), int(S[1][j,i]%CH), int(S[2][j,i]%CH)]
    stack[li] = out
    print(f"layer {off:+3d}: nonzero {(out>0).mean()*100:.0f}% mean {out.mean():.0f} "
          f"chunks {len(cache)} {time.time()-t0:.0f}s", flush=True)
from PIL import Image
best_i = max(range(len(OFFS)), key=lambda i: stack[i].std())
strip = np.concatenate([stack[2], np.full((N,3),255,np.uint8), stack[best_i]], 1)
nzv = strip[strip>0]
lo, hi = (np.percentile(nzv,[2,98]) if nzv.size else (0,255))
img = (np.clip((strip.astype(np.float32)-lo)/max(hi-lo,1),0,1)*255).astype(np.uint8)
Image.fromarray(img).resize((img.shape[1]*3, img.shape[0]*3), Image.LANCZOS).save(
    os.path.join(OUT, "regen_s1_proof.png"))
print("PROOF written: out/regen_s1_proof.png", flush=True)
