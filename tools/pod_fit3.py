"""POD FIT v3 — registration anchored on the PUBLISHED RENDER (unfakeable).

v1 (brightness) was blind at 36 um; v2 (gradient alignment) was gamed by
empty space (align 0.71, brightness 1/255, proof render black). v3 scores a
candidate transform by PEARSON CORRELATION between (a) the segment's own
published L1 surface-volume mid-band — the output of the TRUE transform —
and (b) the native volume sampled at the transformed mesh points. Texture
matching has one global optimum; emptiness correlates to zero.

Correspondence: mesh grid step = 20 level-0 voxels; L1 canvas is a 2x
downsample, so mesh gridpoint (r,c) <-> L1 canvas pixel (r*10, c*10).
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
from itertools import permutations, product
import numpy as np

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOLZ = "PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr"
MESH = ("PHercParis4/segments/20230702185753/mesh/"
        "20230702185753-on-20260608103018-1.129um.tifxyz")
SV = ("PHercParis4/segments/20230702185753/surface-volumes/"
      "1.129um-0.23m-78keV-volume-20260608103018-L1.zarr")
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
L5 = 32.0


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=120):
    return urllib.request.urlopen(u, timeout=t).read()


def fetch_level5():
    za = json.loads(get(f"{B}/{VOLZ}/5/.zarray").decode())
    D, H, W = za["shape"]
    V = np.zeros((D, H, W), np.uint8)
    nz, ny, nx = (D+CH-1)//CH, (H+CH-1)//CH, (W+CH-1)//CH
    got = [0]
    def g(cz, cy, cx):
        try:
            b = get(f"{B}/{VOLZ}/5/{cz}/{cy}/{cx}")
            if len(b) == CH**3:
                a = np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                z1, y1, x1 = min(D,(cz+1)*CH), min(H,(cy+1)*CH), min(W,(cx+1)*CH)
                V[cz*CH:z1, cy*CH:y1, cx*CH:x1] = a[:z1-cz*CH, :y1-cy*CH, :x1-cx*CH]
                got[0] += 1
        except Exception:
            pass
    keys = [(a,b_,c) for a in range(nz) for b_ in range(ny) for c in range(nx)]
    with cf.ThreadPoolExecutor(max_workers=48) as ex:
        list(ex.map(lambda k: g(*k), keys))
    log(f"level5 {V.shape} chunks {got[0]}/{len(keys)} mean {V.mean():.1f}")
    return V


def load_refs():
    """Mesh points from a compact valid region + their TRUE surface values
    from the published L1 render."""
    import tifffile
    X = tifffile.imread(io.BytesIO(get(f"{B}/{MESH}/x.tif", 300)))
    Y = tifffile.imread(io.BytesIO(get(f"{B}/{MESH}/y.tif", 300)))
    Z = tifffile.imread(io.BytesIO(get(f"{B}/{MESH}/z.tif", 300)))
    gh, gw = X.shape
    valid = Z > 0
    # find a 320x320 fully-valid grid window near centre
    N = 320
    r0 = c0 = None
    for rr in range(gh//2 - N, gh//2 + N, 40):
        for cc in range(gw//2 - N, gw//2 + N, 40):
            if rr >= 0 and cc >= 0 and rr+N < gh and cc+N < gw and \
               valid[rr:rr+N, cc:cc+N].all():
                r0, c0 = rr, cc; break
        if r0 is not None: break
    if r0 is None:
        raise RuntimeError("no valid mesh window")
    P = np.stack([X[r0:r0+N, c0:c0+N], Y[r0:r0+N, c0:c0+N],
                  Z[r0:r0+N, c0:c0+N]])
    du = np.gradient(P, axis=2); dv = np.gradient(P, axis=1)
    Nrm = np.cross(du.reshape(3,-1).T, dv.reshape(3,-1).T).T.reshape(P.shape)
    nn = np.linalg.norm(Nrm, axis=0); nn[nn==0] = 1; Nrm /= nn

    # published surface values: mid-band mean of the L1 surface volume at
    # canvas (r*10, c*10) for r,c in the window
    za = json.loads(get(f"{B}/{SV}/0/.zarray").decode())
    Dv, Hv, Wv = za["shape"]
    y0c, x0c = r0*10, c0*10
    cy0, cx0 = y0c//CH, x0c//CH
    cy1, cx1 = (y0c + N*10)//CH + 1, (x0c + N*10)//CH + 1
    Sacc = {}
    def gs(cy, cx):
        try:
            b = get(f"{B}/{SV}/0/0/{cy}/{cx}")   # level/depth-chunk/row/col
            if len(b) == Dv*CH*CH:
                a = np.frombuffer(b, np.uint8).reshape(Dv, CH, CH)
                Sacc[(cy,cx)] = a[Dv//2-4:Dv//2+4].mean(0)   # mid-band mean
        except Exception:
            pass
    keys = [(a,b_) for a in range(cy0, min(cy1, Hv//CH+1))
            for b_ in range(cx0, min(cx1, Wv//CH+1))]
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda k: gs(*k), keys))
    log(f"surface refs: {len(Sacc)}/{len(keys)} chunks, canvas ({y0c},{x0c})")
    rs, cs = np.meshgrid(np.arange(N), np.arange(N), indexing="ij")
    yv, xv = (r0+rs)*10, (c0+cs)*10
    S = np.full((N, N), -1.0, np.float32)
    for j in range(N):
        for i in range(N):
            key = (yv[j,i]//CH, xv[j,i]//CH)
            a = Sacc.get(key)
            if a is not None:
                S[j,i] = a[yv[j,i]%CH, xv[j,i]%CH]
    ok = S >= 0
    idx = np.argwhere(ok)
    sel = idx[np.random.default_rng(7).permutation(len(idx))[:6000]]
    pts = P[:, sel[:,0], sel[:,1]].T
    nrm = Nrm[:, sel[:,0], sel[:,1]].T
    Sv = S[sel[:,0], sel[:,1]]
    log(f"{len(pts)} anchored points, surface value spread "
        f"{Sv.std():.1f} (need >5 for correlation to mean anything)")
    return pts, nrm, Sv


def score_T(V, pts_v, S):
    D, H, W = V.shape
    p5 = pts_v / L5
    inb = ((p5[:,0] > 1) & (p5[:,0] < D-2) & (p5[:,1] > 1) & (p5[:,1] < H-2) &
           (p5[:,2] > 1) & (p5[:,2] < W-2))
    f = float(inb.mean())
    if f < 0.3 or inb.sum() < 500:
        return -1.0, f, 0.0
    q = np.rint(p5[inb]).astype(np.int64)
    v = V[q[:,0], q[:,1], q[:,2]].astype(np.float32)
    s = S[inb]
    if v.std() < 1e-6 or s.std() < 1e-6:
        return -1.0, f, float(v.mean())
    r = float(np.corrcoef(v, s)[0, 1])
    return r * min(f/0.6, 1.0), f, float(v.mean())


SIGNED_PERMS = [(p, sg) for p in permutations(range(3))
                for sg in product((1,-1), repeat=3)]


def main():
    t0 = time.time()
    V = fetch_level5()
    pts, nrm, S = load_refs()
    dims = np.array(V.shape) * L5
    results = []
    for scale in (0.5, 1.0):
        for perm, sign in SIGNED_PERMS:
            q0 = pts[:, list(perm)] * (np.array(sign) * scale)
            lo, hi = q0.min(0), q0.max(0)
            steps = []
            for a in range(3):
                tmin, tmax = -hi[a] + dims[a]*0.1, -lo[a] + dims[a]*0.9
                k = max(2, min(8, int((tmax - tmin)//5000) + 1))
                steps.append([tmin + (tmax-tmin)*j/(k-1) for j in range(k)])
            for t in product(*steps):
                sc, f, br = score_T(V, q0 + np.array(t), S)
                if sc > 0.05:
                    results.append((sc, f, br, perm, sign, scale,
                                    tuple(round(float(x),1) for x in t)))
    results.sort(reverse=True)
    log(f"coarse: {len(results)} configs with corr>0.05 in {time.time()-t0:.0f}s")
    for r in results[:6]:
        log(f"  corr {r[0]:+.3f} inb {r[1]:.2f} bright {r[2]:.0f} "
            f"perm {r[3]} sign {r[4]} s {r[5]} t {r[6]}")
    if not results:
        log("NO correlated config found — texture anchor failed at level 5")
        json.dump(dict(done=True, found=False), open(os.path.join(OUT,"done.json"),"w"))
        return
    sc, f, br, perm, sign, scale, t = results[0]
    t = np.array(t, float)
    q0 = pts[:, list(perm)] * (np.array(sign) * scale)
    best = sc
    for step in (2560, 640, 160, 40):
        improved = True
        while improved:
            improved = False
            for a in range(3):
                for d in (-step, step):
                    tt = t.copy(); tt[a] += d
                    s2, _, _ = score_T(V, q0 + tt, S)
                    if s2 > best:
                        best, t, improved = s2, tt, True
            for ds in (0.985, 1.015):
                s2, _, _ = score_T(V, q0*ds + t, S)
                if s2 > best:
                    best, q0, scale, improved = s2, q0*ds, scale*ds, True
    sc, f, br = score_T(V, q0 + t, S)
    log(f"REFINED corr {sc:+.3f} inb {f:.2f} bright {br:.0f} "
        f"perm {perm} sign {sign} scale {scale:.4f} t {t.round(1).tolist()}")
    json.dump(dict(perm=list(perm), sign=[int(x) for x in sign],
                   scale=float(scale), t=[float(x) for x in t],
                   corr=float(sc), inbounds=float(f), bright=float(br)),
              open(os.path.join(OUT, "transform.json"), "w"), indent=1)
    json.dump(dict(done=True, found=True, corr=float(sc)),
              open(os.path.join(OUT, "done.json"), "w"))
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED — see error.txt")
