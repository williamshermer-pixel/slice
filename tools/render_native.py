#!/usr/bin/env python3
"""Render a surface volume OURSELVES, at 1.129 um — the resolution nobody has used.

WHY THIS EXISTS. Vesuvius Challenge's own docs say plainly: "We have evidence
that working on 1.1 um data yields cleaner results than 2.4 um data." And the
thing that finally broke PHerc. 1667 open after two years of nothing was not a
better model — it was a better scan, re-unwrapped at higher resolution and fed
to the generalist detector.

Every render this project has ever used is a published `-L1` surface volume,
whose finest level is 2.258 um. The "L1" is literal: level ONE, a 2x downsample
of the 1.129 um scan. We have never once looked at level 0.

Both halves are published and nobody has joined them:
  * raw scan   PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr
               (1.129 um, 0.2 m propagation, 78 keV -- the optimal recipe)
  * the mesh   37 of 80 Scroll 1 segments carry a tifxyz registered to that
               exact volume: <seg>-on-20260608103018-1.129um.tifxyz

So this samples the raw volume along each mesh cell's surface normal and writes
the 62-layer band the ink models expect.

THE GEOMETRY, AND THE TRAP IN IT
--------------------------------
For each mesh cell we have a 3D point P and a unit surface normal N, both in the
scan's voxel grid. Layer k of the surface volume is the volume sampled at

    P + (k - D/2) * step * N

Their own renderer carries a warning in the source about this exact line: the
normal step must advance ONE VOXEL of the level being read. Scale it by the
downsample factor and you get a stack that is silently anisotropic -- right
shape, wrong physical spacing -- which the model reads as a squashed sheet and
answers with nothing. No error, no warning. Same failure class as getting layer
order backwards.

Normals are taken on the mesh INTERIOR and diffused outward, because central
differences at a patch boundary straddle the zero-fill and collapse (measured:
0 of 694 rim cells had a usable normal on Scroll 1 seg 20231005123336).

    python3 tools/render_native.py --segment 20231005123336 --out out/native
"""
import argparse
import concurrent.futures as cf
import io
import json
import os
import urllib.error
import urllib.request

import numpy as np
from scipy import ndimage

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
UA = {"User-Agent": "Mozilla/5.0"}

SCROLL = "PHercParis4"
VOLID = "20260608103018-1.129um"
RAWVOL = f"{B}/{SCROLL}/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr"
D = 62


def get(url, timeout=180):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def load_mesh(seg):
    import tifffile
    sid = seg[:14]
    base = f"{B}/{SCROLL}/segments/{seg}/mesh/{sid}-on-{VOLID}.tifxyz"
    meta = json.loads(get(f"{base}/meta.json").decode())
    a = [tifffile.imread(io.BytesIO(get(f"{base}/{ax}.tif", 600))).astype(np.float32)
         for ax in "xyz"]
    xyz = np.stack(a, -1)
    return xyz, valid_mask(xyz), meta


def valid_mask(xyz):
    """Cells that hold a real 3D position.

    THE SENTINEL IS -1, NOT 0. Measured 2026-08-02 on Scroll 1 seg
    20231012184424: `xyz[350,350] == [-1,-1,-1]`, and the naive test
    `(xyz != 0).any(-1)` calls that VALID, because -1 is not 0. The mesh then
    reports 100% coverage, an empty crop looks full, du/dv come out identically
    zero, every normal collapses, and the render silently produces an all-zero
    stack with no error anywhere.

    Both sentinels are excluded here because different tifxyz generations use
    different fill.
    """
    return ~(((xyz == -1).all(-1)) | ((xyz == 0).all(-1)))


def normals(xyz, valid):
    """Interior normals, diffused outward to reach the rim."""
    du = np.zeros_like(xyz)
    dv = np.zeros_like(xyz)
    du[:, 1:-1] = xyz[:, 2:] - xyz[:, :-2]
    dv[1:-1, :] = xyz[2:] - xyz[:-2]
    n = np.cross(du, dv)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-6)
    er = ndimage.binary_erosion(valid, np.ones((3, 3), bool), border_value=0)
    interior = valid & er & (np.linalg.norm(n, axis=-1) > 0.5)
    n[~interior] = 0
    sm = np.stack([ndimage.uniform_filter(n[..., k], 9) for k in range(3)], -1)
    l2 = np.linalg.norm(sm, axis=-1, keepdims=True)
    sm = np.divide(sm, l2, out=np.zeros_like(sm), where=l2 > 1e-6)
    return np.where(interior[..., None], n, sm)


class Volume:
    """Chunk-cached reader for an uncompressed uint8 OME-Zarr level."""

    def __init__(self, url, level=0):
        self.url = f"{url}/{level}"
        za = json.loads(get(f"{self.url}/.zarray").decode())
        assert za["dtype"] == "|u1" and za["compressor"] is None, za
        self.shape = za["shape"]
        self.chunks = za["chunks"]
        self.cache = {}
        self.miss = 0
        self.hit = 0

    def chunk(self, cz, cy, cx):
        k = (cz, cy, cx)
        if k in self.cache:
            self.hit += 1
            return self.cache[k]
        self.miss += 1
        try:
            raw = get(f"{self.url}/{cz}/{cy}/{cx}", 300)
            a = np.frombuffer(raw, np.uint8)
            v = a.reshape(self.chunks) if a.size == int(np.prod(self.chunks)) else None
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404):
                raise
            v = None                      # sparse: never written
        if len(self.cache) > 4000:
            self.cache.clear()
        self.cache[k] = v
        return v

    def sample(self, pts):
        """Nearest-neighbour sample at integer voxel coords, (N,3) z,y,x."""
        out = np.zeros(len(pts), np.uint8)
        p = np.rint(pts).astype(np.int64)
        ok = np.ones(len(p), bool)
        for d in range(3):
            ok &= (p[:, d] >= 0) & (p[:, d] < self.shape[d])
        idx = np.where(ok)[0]
        if not len(idx):
            return out
        cz, cy, cx = self.chunks
        key = np.stack([p[idx, 0] // cz, p[idx, 1] // cy, p[idx, 2] // cx], 1)
        order = np.lexsort((key[:, 2], key[:, 1], key[:, 0]))
        idx, key = idx[order], key[order]
        start = 0
        for i in range(1, len(idx) + 1):
            if i == len(idx) or (key[i] != key[start]).any():
                blk = self.chunk(*key[start])
                if blk is not None:
                    sel = idx[start:i]
                    out[sel] = blk[p[sel, 0] % cz, p[sel, 1] % cy, p[sel, 2] % cx]
                start = i
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segment", required=True)
    ap.add_argument("--out", default="out/native")
    ap.add_argument("--crop", type=int, nargs=4, metavar=("R0", "C0", "H", "W"),
                    help="mesh-grid crop; default a centred 320x320 window")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="mesh upsample factor; 20 => 1.129 um/px, 10 => 2.258")
    ap.add_argument("--step", type=float, default=1.0,
                    help="normal step in LEVEL-0 VOXELS (do not rescale)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    import re
    segs = json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "public", "ink-maps.json")))
    full = next((e["segment"] for e in segs["entries"]
                 if e["scroll"] == SCROLL and e["segment"].startswith(args.segment)),
                args.segment)

    xyz, valid, meta = load_mesh(full)
    print(f"mesh {valid.shape}  valid {valid.sum():,}  scale {meta.get('scale')}")
    nrm = normals(xyz, valid)

    H, W = valid.shape
    if args.crop:
        r0, c0, h, w = args.crop
    else:
        h = w = min(320, H, W)
        r0, c0 = (H - h) // 2, (W - w) // 2
    r1, c1 = min(H, r0 + h), min(W, c0 + w)
    print(f"crop rows {r0}:{r1} cols {c0}:{c1}")

    P = xyz[r0:r1, c0:c1]
    N = nrm[r0:r1, c0:c1]
    M = valid[r0:r1, c0:c1] & (np.linalg.norm(N, axis=-1) > 0.5)
    print(f"usable mesh cells {M.sum():,}/{M.size:,}")

    # UPSAMPLE THE MESH TO THE TARGET RESOLUTION.
    #
    # The tifxyz grid is `scale` 0.05 — one mesh cell per 20 volume voxels — so
    # sampling at mesh resolution renders at 22.6 um/px, which is COARSER than
    # the published 2.258 um volumes, not finer. Rendering at 1.129 um means
    # interpolating the position and normal fields up by 20x and sampling the
    # volume at every one of those points. `--scale` is that factor: 20 gives
    # 1.129 um/px, 10 gives 2.258 um/px (parity with what is published).
    #
    # Physical extent is set by the MESH CROP, not by scale: upsampling buys
    # finer pixels over the same patch of papyrus, never a wider view.
    s = args.scale
    if s != 1:
        from scipy.ndimage import map_coordinates
        h0, w0 = M.shape
        rr = np.linspace(0, h0 - 1, int(h0 * s))
        cc = np.linspace(0, w0 - 1, int(w0 * s))
        gr, gc = np.meshgrid(rr, cc, indexing="ij")
        co = np.stack([gr, gc])
        P = np.stack([map_coordinates(P[..., k], co, order=1, mode="nearest")
                      for k in range(3)], -1)
        N = np.stack([map_coordinates(N[..., k], co, order=1, mode="nearest")
                      for k in range(3)], -1)
        ln = np.linalg.norm(N, axis=-1, keepdims=True)
        N = np.divide(N, ln, out=np.zeros_like(N), where=ln > 1e-6)
        M = map_coordinates(M.astype(np.float32), co, order=1,
                            mode="nearest") > 0.99
        print(f"upsampled x{s} -> {M.shape}  "
              f"{1.129 * 20 / s:.3f} um/px  "
              f"{M.shape[0] * 1.129 * 20 / s / 1000:.2f} mm across")
    hh, ww = M.shape

    vol = Volume(RAWVOL, 0)
    print(f"raw volume {vol.shape} chunks {vol.chunks}")

    stack = np.zeros((hh, ww, D), np.uint8)
    ys, xs = np.where(M)
    base = P[ys, xs]                      # (n,3) in volume voxel coords (x,y,z?)
    nn = N[ys, xs]
    for k in range(D):
        off = (k - D / 2.0) * args.step
        pts = base + nn * off
        # tifxyz stores (x, y, z); the zarr is indexed (z, y, x)
        stack[ys, xs, k] = vol.sample(pts[:, ::-1])
        if k % 10 == 0:
            print(f"  layer {k}/{D}  chunks fetched {vol.miss} cached {vol.hit}",
                  flush=True)

    np.save(os.path.join(args.out, f"{args.segment}_stack.npy"), stack)
    nz = stack[stack > 0]
    print(f"stack {stack.shape}  nonzero {100*(stack>0).mean():.1f}%  "
          f"mean {nz.mean():.1f}" if nz.size else "stack all zero")
    print(f"chunks fetched {vol.miss}, cache hits {vol.hit}")
    print("->", os.path.join(args.out, f"{args.segment}_stack.npy"))


if __name__ == "__main__":
    main()
