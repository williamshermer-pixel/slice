"""POD FIT — recover the unpublished mesh->volume registration, on a pod.

The field's own source says tifxyz coords are plain voxel coords bridged by
an external affine that was never published for Scroll 1's native volume
(HANDOFF 2026-07-29). This job fits it empirically:

  1. fetch the ENTIRE native volume at pyramid level 5 (36 um, ~2 GB) into RAM
  2. sample the segment mesh sparsely, with normals
  3. coarse-search signed axis permutations x scale x translation, scoring
     in-bounds fraction + sheet brightness + profile peakedness
  4. refine the winner by coordinate descent
  5. proof-render a patch at level 2 with the fitted transform
  6. serve transform.json + renders on :8000
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
from itertools import permutations, product
import numpy as np

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOLZ = "PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr"
MESH = ("PHercParis4/segments/20230702185753/mesh/"
        "20230702185753-on-20260608103018-1.129um.tifxyz")
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
L5 = 32.0            # level-5 downsample factor


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=120):
    return urllib.request.urlopen(u, timeout=t).read()


def fetch_level5():
    za = json.loads(get(f"{B}/{VOLZ}/5/.zarray").decode())
    D, H, W = za["shape"]
    V = np.zeros((D, H, W), np.uint8)
    nz, ny, nx = (D + CH - 1)//CH, (H + CH - 1)//CH, (W + CH - 1)//CH
    got = [0]

    def g(cz, cy, cx):
        try:
            b = get(f"{B}/{VOLZ}/5/{cz}/{cy}/{cx}")
            if len(b) == CH**3:
                a = np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                z1, y1, x1 = min(D, (cz+1)*CH), min(H, (cy+1)*CH), min(W, (cx+1)*CH)
                V[cz*CH:z1, cy*CH:y1, cx*CH:x1] = \
                    a[:z1-cz*CH, :y1-cy*CH, :x1-cx*CH]
                got[0] += 1
        except Exception:
            pass

    keys = [(a, b_, c) for a in range(nz) for b_ in range(ny) for c in range(nx)]
    with cf.ThreadPoolExecutor(max_workers=48) as ex:
        list(ex.map(lambda k: g(*k), keys))
    log(f"level5 {V.shape} chunks {got[0]}/{len(keys)} "
        f"mean {V.mean():.1f} nonzero {(V>0).mean()*100:.0f}%")
    return V


def load_mesh():
    import tifffile
    arrs = {}
    for ax in "xyz":
        raw = get(f"{B}/{MESH}/{ax}.tif", 300)
        arrs[ax] = tifffile.imread(io.BytesIO(raw))
    X, Y, Z = arrs["x"], arrs["y"], arrs["z"]
    valid = Z > 0
    P = np.stack([X, Y, Z])                       # mesh-native XYZ order
    du = np.gradient(P, axis=2); dv = np.gradient(P, axis=1)
    Nrm = np.cross(du.reshape(3, -1).T, dv.reshape(3, -1).T).T.reshape(P.shape)
    nn = np.linalg.norm(Nrm, axis=0); nn[nn == 0] = 1
    Nrm = Nrm / nn
    ok = valid & (np.abs(Nrm).sum(0) > 0.5)
    idx = np.argwhere(ok)
    sel = idx[np.random.default_rng(7).permutation(len(idx))[:6000]]
    pts = P[:, sel[:, 0], sel[:, 1]].T            # (N,3) xyz mesh order
    nrm = Nrm[:, sel[:, 0], sel[:, 1]].T
    log(f"mesh grid {X.shape}, {len(pts)} sample points")
    return pts, nrm


SIGNED_PERMS = [(p, s) for p in permutations(range(3))
                for s in product((1, -1), repeat=3)]


def apply_T(pts, perm, sign, scale, t, dims):
    # mesh xyz -> volume (z,y,x) axes: axis i of volume takes mesh coord perm[i]
    q = pts[:, list(perm)] * (np.array(sign) * scale)
    q = q + np.array(t)
    return q                                       # (N,3) in volume z,y,x


def score_T(V, pts_v, nrm_v):
    """Normal-gradient alignment. v1 scored brightness+peakedness and the
    landscape was FLAT (every config ~87): at 36 um the windings blur into
    near-uniform soup. But the LAYERING DIRECTION survives blurring — in a
    layered medium the intensity gradient points across the sheets, so a
    correct registration aligns mesh normals with local gradients. Random
    alignment of |cos| in 3D averages 0.5; layered-aligned runs 0.7+.
    Partial containment ALLOWED (the volume is a crop; the true fit may
    hang outside) — score on the in-bounds subset, require >=25%."""
    D, H, W = V.shape
    p5 = pts_v / L5
    inb = ((p5[:, 0] > 2) & (p5[:, 0] < D-3) &
           (p5[:, 1] > 2) & (p5[:, 1] < H-3) &
           (p5[:, 2] > 2) & (p5[:, 2] < W-3))
    f = float(inb.mean())
    if f < 0.25 or inb.sum() < 400:
        return -1.0, f, 0.0, 0.0
    q = p5[inb]; n = nrm_v[inb]
    def samp(pp):
        i = np.rint(pp).astype(np.int64)
        return V[i[:, 0], i[:, 1], i[:, 2]].astype(np.float32)
    g = np.stack([samp(q + e) - samp(q - e)
                  for e in np.eye(3)], axis=1)          # (N,3) gradient
    gn = np.linalg.norm(g, axis=1)
    w = gn > 2.0                                        # meaningful gradients
    if w.sum() < 200:
        return -1.0, f, 0.0, 0.0
    align = np.abs((g[w] * n[w]).sum(1)) / (gn[w] + 1e-9)
    bright = float(samp(q).mean())
    a = float(align.mean())
    # alignment is the discriminator; brightness a mild tiebreak
    return a * min(f / 0.6, 1.0) + bright / 2550.0, f, bright, a


def main():
    t0 = time.time()
    V = fetch_level5()
    pts, nrm = load_mesh()
    dims = np.array(V.shape) * L5

    results = []
    for scale in (0.5, 1.0):
        for perm, sign in SIGNED_PERMS:
            q0 = pts[:, list(perm)] * (np.array(sign) * scale)
            n0 = nrm[:, list(perm)] * np.array(sign)
            lo, hi = q0.min(0), q0.max(0)
            # PARTIAL containment: slide over the full overlap range —
            # the cropped volume may hold only part of the mesh.
            steps = []
            for a in range(3):
                tmin, tmax = -hi[a] + dims[a]*0.25, -lo[a] + dims[a]*0.75
                k = max(2, min(7, int((tmax - tmin) // 6000) + 1))
                steps.append([tmin + (tmax - tmin) * j / (k - 1)
                              for j in range(k)])
            for t in product(*steps):
                s, f, br, pk = score_T(V, q0 + np.array(t), n0)
                if s > 0:
                    results.append((float(s), float(f), float(br), float(pk),
                                    perm, sign, scale,
                                    tuple(round(float(v), 1) for v in t)))
    results.sort(reverse=True)
    log(f"coarse done: {len(results)} feasible configs in {time.time()-t0:.0f}s")
    for r in results[:5]:
        log(f"  score {r[0]:.1f} inb {r[1]:.2f} bright {r[2]:.0f} peak {r[3]:.1f} "
            f"perm {r[4]} sign {r[5]} s {r[6]} t {r[7]}")
    if not results:
        log("NO feasible config"); return

    # refine winner: coordinate descent on translation + scale
    _, _, _, _, perm, sign, scale, t = results[0]
    t = np.array(t, float)
    q0 = pts[:, list(perm)] * (np.array(sign) * scale)
    n0 = nrm[:, list(perm)] * np.array(sign)
    best, *_ = score_T(V, q0 + t, n0)
    for step in (2048, 512, 128, 32):
        improved = True
        while improved:
            improved = False
            for a in range(3):
                for d in (-step, step):
                    tt = t.copy(); tt[a] += d
                    s, *_ = score_T(V, q0 + tt, n0)
                    if s > best:
                        best, t, improved = s, tt, True
            for ds in (0.98, 1.02):
                qq = q0 * ds
                s, *_ = score_T(V, qq + t, n0)
                if s > best:
                    best, scale, q0, improved = s, scale*ds, qq, True
    s, f, br, pk = score_T(V, q0 + t, n0)
    log(f"REFINED score {s:.1f} inb {f:.2f} bright {br:.0f} peak {pk:.1f} "
        f"perm {perm} sign {sign} scale {scale:.4f} t {t.round(1).tolist()}")
    json.dump(dict(perm=list(perm), sign=[int(x) for x in sign],
                   scale=float(scale), t=[float(x) for x in t],
                   score=float(s), inbounds=float(f), bright=float(br),
                   align=float(pk)),
              open(os.path.join(OUT, "transform.json"), "w"), indent=1)

    # proof render at level 2 (4.516 um): a 300x300 mesh-point patch
    import tifffile
    from PIL import Image
    za2 = json.loads(get(f"{B}/{VOLZ}/2/.zarray").decode())
    D2, H2, W2 = za2["shape"]
    Xg = tifffile.imread(io.BytesIO(get(f"{B}/{MESH}/x.tif", 300)))
    Yg = tifffile.imread(io.BytesIO(get(f"{B}/{MESH}/y.tif", 300)))
    Zg = tifffile.imread(io.BytesIO(get(f"{B}/{MESH}/z.tif", 300)))
    gh, gw = Xg.shape
    N = 300
    y0, x0 = gh//2 - N//2, gw//2 - N//2
    Pg = np.stack([Xg[y0:y0+N, x0:x0+N], Yg[y0:y0+N, x0:x0+N],
                   Zg[y0:y0+N, x0:x0+N]])
    du = np.gradient(Pg, axis=2); dv = np.gradient(Pg, axis=1)
    Ng_ = np.cross(du.reshape(3, -1).T, dv.reshape(3, -1).T).T.reshape(Pg.shape)
    nn = np.linalg.norm(Ng_, axis=0); nn[nn == 0] = 1; Ng_ /= nn
    Pv = (Pg.reshape(3, -1).T[:, list(perm)] * (np.array(sign)*scale) + t)
    Nv = Ng_.reshape(3, -1).T[:, list(perm)] * np.array(sign)
    cache = {}
    def chunk2(cz, cy, cx):
        key = (cz, cy, cx)
        if key not in cache:
            try:
                b = get(f"{B}/{VOLZ}/2/{cz}/{cy}/{cx}")
                cache[key] = (np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                              if len(b) == CH**3 else None)
            except Exception:
                cache[key] = None
        return cache[key]
    layers = []
    for off in (-16, 0, 16):                      # level-0 voxels along normal
        Sp = (Pv + Nv * off) / 4.0                # level 2
        Si = np.rint(Sp).astype(np.int64)
        Si[:, 0] = Si[:, 0].clip(0, D2-1); Si[:, 1] = Si[:, 1].clip(0, H2-1)
        Si[:, 2] = Si[:, 2].clip(0, W2-1)
        ck = Si // CH
        keys = set(map(tuple, ck.tolist()))
        with cf.ThreadPoolExecutor(max_workers=32) as ex:
            list(ex.map(lambda k: chunk2(*k), keys))
        vals = np.zeros(len(Si), np.uint8)
        for j in range(len(Si)):
            c = cache.get(tuple(ck[j]))
            if c is not None:
                r = Si[j] % CH
                vals[j] = c[r[0], r[1], r[2]]
        layers.append(vals.reshape(N, N))
        log(f"  render layer {off:+d}: nonzero {(vals>0).mean()*100:.0f}%")
    strip = np.concatenate([layers[0], np.full((N, 3), 255, np.uint8),
                            layers[1], np.full((N, 3), 255, np.uint8),
                            layers[2]], axis=1)
    nzv = strip[strip > 0]
    lo, hi = (np.percentile(nzv, [2, 98]) if nzv.size else (0, 255))
    img = (np.clip((strip.astype(np.float32)-lo)/max(hi-lo, 1), 0, 1)*255).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1]*3, img.shape[0]*3),
                                Image.LANCZOS).save(os.path.join(OUT, "fit_proof.png"))
    json.dump(dict(done=True, score=float(s), scale=float(scale)),
              open(os.path.join(OUT, "done.json"), "w"))
    log("DONE — transform.json + fit_proof.png")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED — see error.txt")
