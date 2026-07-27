"""Comb a scroll in 3D with a swarm of walkers, and export it for Blender.

Runs the 2D sheet-walker across a stack of consecutive slices. Tracing the same
winding on many slices gives a stack of contours, and a stack of contours IS the
sheet — the same way medical imaging reconstructs a surface from cross sections.

One chunk fetch serves 128 slices, so a whole stack costs the same as one slice.

Exports:
  tracks.obj        polylines, importable anywhere (Blender: File > Import > OBJ)
  tracks.csv        raw points, if you'd rather build your own
  blender_import.py run inside Blender to load, colour and rig a flythrough
"""
import urllib.request, concurrent.futures as cf, sys
import numpy as np
from PIL import Image

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOL = "PHerc0800/volumes/20250521135224-8.640um-1.2m-116keV-masked.zarr"
CH, UM = 128, 8.64
ZC = int(sys.argv[1]) if len(sys.argv) > 1 else 92       # chunk index in z
CY, CX, N = 45, 28, 5
NSLICES = int(sys.argv[2]) if len(sys.argv) > 2 else 16
SSTEP = int(sys.argv[3]) if len(sys.argv) > 3 else 8


def fetch_block():
    """One fetch of the chunk band; every slice in it is then free."""
    vol = np.zeros((CH, N*CH, N*CH), np.uint8); got = 0
    def g(cy, cx):
        try:
            with urllib.request.urlopen(f"{B}/{VOL}/0/{ZC}/{cy}/{cx}", timeout=180) as r:
                b = r.read()
            return cy, cx, (np.frombuffer(b, np.uint8).reshape(CH, CH, CH) if len(b) == CH**3 else None)
        except Exception:
            return cy, cx, None
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for cy, cx, a in ex.map(lambda p: g(*p), [(CY+j, CX+i) for j in range(N) for i in range(N)]):
            if a is not None:
                got += 1
                vol[:, (cy-CY)*CH:(cy-CY+1)*CH, (cx-CX)*CH:(cx-CX+1)*CH] = a
    return vol, got


def box(a, r):
    k = 2*r+1
    c = np.cumsum(np.pad(a.astype(np.float32), ((r+1, r), (0, 0)), mode="edge"), axis=0)
    o = (c[k:]-c[:-k])/k
    c = np.cumsum(np.pad(o, ((0, 0), (r+1, r)), mode="edge"), axis=1)
    return (c[:, k:]-c[:, :-k])/k


def comb(img):
    H, W = img.shape
    ridge = img - box(img, 6)
    ridge[img == 0] = -1e3
    gy, gx = np.gradient(ridge)
    Jxx = box(gx*gx, 4); Jyy = box(gy*gy, 4); Jxy = box(gx*gy, 4)
    th = 0.5*np.arctan2(2*Jxy, Jxx-Jyy)
    coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2)/np.maximum(Jxx+Jyy, 1e-6)
    dirx, diry = -np.sin(th), np.cos(th)

    def S(F, y, x):
        yi, xi = int(round(y)), int(round(x))
        if yi < 1 or xi < 1 or yi >= H-1 or xi >= W-1: return None
        return F[yi, xi]

    def drive(y, x, sign):
        t = [(y, x)]; vy = vx = None
        for _ in range(1500):
            c, r = S(coh, y, x), S(ridge, y, x)
            if c is None or c < 0.25 or r is None or r < 0.5: break
            dy, dx = S(diry, y, x), S(dirx, y, x)
            if dy is None: break
            if vy is not None and (dy*vy + dx*vx) < 0: dy, dx = -dy, -dx
            vy, vx = dy, dx
            ny, nx = y + sign*dy, x + sign*dx
            py, px = -dx, dy
            best, bo = None, 0.0
            for o in np.linspace(-2, 2, 9):
                v = S(ridge, ny+py*o, nx+px*o)
                if v is not None and (best is None or v > best): best, bo = v, o
            ny, nx = ny+py*bo, nx+px*bo
            if not (1 <= ny < H-1 and 1 <= nx < W-1): break
            y, x = ny, nx; t.append((y, x))
        return t

    cand = []
    for y in range(10, H-10, 12):
        for x in range(10, W-10, 12):
            if ridge[y, x] > 3 and coh[y, x] > 0.4: cand.append((float(ridge[y, x]), y, x))
    cand.sort(reverse=True)
    taken = np.zeros((H//12+2, W//12+2), bool); out = []
    for _, y, x in cand:
        gy_, gx_ = y//12, x//12
        if taken[gy_, gx_]: continue
        taken[max(0, gy_-1):gy_+2, max(0, gx_-1):gx_+2] = True
        t = drive(y, x, +1) + drive(y, x, -1)[::-1]
        if len(t) >= 40: out.append(t)
        if len(out) >= 250: break
    return out


vol, got = fetch_block()
print(f"fetched {got}/{N*N} chunks (one band serves all {CH} slices)")
all_tracks = []
for i in range(NSLICES):
    off = i*SSTEP
    if off >= CH: break
    tr = comb(vol[off].astype(np.float32))
    z = ZC*CH + off
    for t in tr:
        all_tracks.append((z, t))
    print(f"  slice z={z}: {len(tr)} tracks")

lens = np.array([len(t) for _, t in all_tracks])
print(f"\n{len(all_tracks)} tracks total, {lens.sum()*UM/1000:.0f} mm of sheet traced")
print(f"track length: median {np.median(lens):.0f} steps ({np.median(lens)*UM/1000:.2f} mm)")

# ---- export ---------------------------------------------------------------
# Blender is Z-up and metres-ish; scale voxels to millimetres so the scene has
# real dimensions and the camera clipping planes behave.
S = UM/1000.0
with open("tracks.obj", "w") as f:
    f.write("# Herculaneum sheet tracks — PHerc.0800, swarm-combed from raw slices\n")
    f.write(f"# {len(all_tracks)} tracks, units = mm\n")
    vi = 1
    for z, t in all_tracks:
        idx = []
        for (y, x) in t:
            f.write(f"v {x*S:.4f} {y*S:.4f} {z*S:.4f}\n")
            idx.append(vi); vi += 1
        for a, b in zip(idx, idx[1:]):
            f.write(f"l {a} {b}\n")
print(f"wrote tracks.obj ({vi-1} points)")

with open("tracks.csv", "w") as f:
    f.write("track,z_mm,y_mm,x_mm\n")
    for i, (z, t) in enumerate(all_tracks):
        for (y, x) in t:
            f.write(f"{i},{z*S:.4f},{y*S:.4f},{x*S:.4f}\n")
print("wrote tracks.csv")
