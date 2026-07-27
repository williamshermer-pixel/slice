"""Render a surface volume for PHerc.1447 segment 20250502205333.

3.54 cm2, 100% of its mesh backed by stored voxels — the best target found in
the coverage sweep, on a scroll nobody has read.

tifxyz gives (u,v) -> (x,y,z). We upsample that to voxel resolution, take the
surface normal, and trilinearly sample the raw volume at p + t*n. The result is
a flattened layer stack: the thing ink models consume, which does not currently
exist in public for this scroll.
"""
import sys, urllib.request, concurrent.futures as cf
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOL = "PHerc0800/volumes/20250521135224-8.640um-1.2m-116keV-masked.zarr"
UM, CH, STEP = 8.64, 128, 20

GU0, GV0, GN, T = (int(a) for a in sys.argv[1:5])
OUT = sys.argv[5]
BUDGET = int(sys.argv[6]) if len(sys.argv) > 6 else 900

X = np.array(Image.open("g_x.tif")).astype(np.float64)
Y = np.array(Image.open("g_y.tif")).astype(np.float64)
Z = np.array(Image.open("g_z.tif")).astype(np.float64)
valid = (X > 0) & (Y > 0) & (Z > 0)

sub = (slice(GV0, GV0 + GN), slice(GU0, GU0 + GN))
print(f"patch v={GV0} u={GU0} n={GN}, validity {100*valid[sub].mean():.0f}%")
if valid[sub].mean() < 0.999:
    print("  (patch contains invalid points — they will render as holes)")
Xs, Ys, Zs = X[sub], Y[sub], Z[sub]


def up(a, f):
    h, w = a.shape
    yy = np.linspace(0, h - 1, h * f); xx = np.linspace(0, w - 1, w * f)
    y0 = np.floor(yy).astype(int); y1 = np.minimum(y0 + 1, h - 1); fy = (yy - y0)[:, None]
    x0 = np.floor(xx).astype(int); x1 = np.minimum(x0 + 1, w - 1); fx = (xx - x0)[None, :]
    return (a[np.ix_(y0, x0)] * (1 - fy) * (1 - fx) + a[np.ix_(y1, x0)] * fy * (1 - fx)
            + a[np.ix_(y0, x1)] * (1 - fy) * fx + a[np.ix_(y1, x1)] * fy * fx)


Xf, Yf, Zf = up(Xs, STEP), up(Ys, STEP), up(Zs, STEP)
SH, SW = Xf.shape
print(f"sheet {SH}x{SW} voxels = {SH*UM/1000:.1f} x {SW*UM/1000:.1f} mm")

Tux, Tuy, Tuz = np.gradient(Xf, axis=1), np.gradient(Yf, axis=1), np.gradient(Zf, axis=1)
Tvx, Tvy, Tvz = np.gradient(Xf, axis=0), np.gradient(Yf, axis=0), np.gradient(Zf, axis=0)
Nx = Tuy * Tvz - Tuz * Tvy; Ny = Tuz * Tvx - Tux * Tvz; Nz = Tux * Tvy - Tuy * Tvx
L = np.sqrt(Nx**2 + Ny**2 + Nz**2) + 1e-9
Nx, Ny, Nz = Nx / L, Ny / L, Nz / L

depths = np.arange(-T, T + 1, dtype=np.float64)
px = Xf[None] + depths[:, None, None] * Nx[None]
py = Yf[None] + depths[:, None, None] * Ny[None]
pz = Zf[None] + depths[:, None, None] * Nz[None]
lo = [int(np.floor(v.min())) - 1 for v in (pz, py, px)]
hi = [int(np.ceil(v.max())) + 2 for v in (pz, py, px)]
cz0, cy0, cx0 = [l // CH for l in lo]
cz1, cy1, cx1 = [(h // CH) + 1 for h in hi]
n = (cz1 - cz0) * (cy1 - cy0) * (cx1 - cx0)
print(f"chunks {cz1-cz0}x{cy1-cy0}x{cx1-cx0} = {n} ({n*2} MB max)")
if n > BUDGET:
    print(f"ABORT: over {BUDGET}-chunk budget"); raise SystemExit(1)

dense = np.zeros(((cz1-cz0)*CH, (cy1-cy0)*CH, (cx1-cx0)*CH), np.uint8)
print(f"buffer {dense.nbytes/1e6:.0f} MB")

def get(cz, cy, cx):
    try:
        with urllib.request.urlopen(f"{B}/{VOL}/0/{cz}/{cy}/{cx}", timeout=180) as r:
            b = r.read()
        return cz, cy, cx, (np.frombuffer(b, np.uint8).reshape(CH, CH, CH) if len(b) == CH**3 else None)
    except Exception:
        return cz, cy, cx, None

jobs = [(z, y, x) for z in range(cz0, cz1) for y in range(cy0, cy1) for x in range(cx0, cx1)]
got = 0
with cf.ThreadPoolExecutor(max_workers=24) as ex:
    for cz, cy, cx, a in ex.map(lambda p: get(*p), jobs):
        if a is not None:
            got += 1
            dense[(cz-cz0)*CH:(cz-cz0+1)*CH, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
print(f"fetched {got}/{len(jobs)} chunks ({100*got/len(jobs):.0f}%)")

gz = pz - cz0*CH; gy = py - cy0*CH; gx = px - cx0*CH
z0 = np.clip(np.floor(gz).astype(np.int32), 0, dense.shape[0]-2)
y0 = np.clip(np.floor(gy).astype(np.int32), 0, dense.shape[1]-2)
x0 = np.clip(np.floor(gx).astype(np.int32), 0, dense.shape[2]-2)
fz, fy, fx = gz-z0, gy-y0, gx-x0
def V(a, b, c): return dense[z0+a, y0+b, x0+c].astype(np.float32)
out = (V(0,0,0)*(1-fz)*(1-fy)*(1-fx) + V(1,0,0)*fz*(1-fy)*(1-fx)
     + V(0,1,0)*(1-fz)*fy*(1-fx) + V(0,0,1)*(1-fz)*(1-fy)*fx
     + V(1,1,0)*fz*fy*(1-fx) + V(1,0,1)*fz*(1-fy)*fx
     + V(0,1,1)*(1-fz)*fy*fx + V(1,1,1)*fz*fy*fx).astype(np.uint8)
print(f"surface volume {out.shape}, nonzero {100*(out>0).mean():.1f}%")
np.save(OUT + ".npy", out)

def n8(a):
    nz = a[a > 0]
    if nz.size < 100: return np.zeros(a.shape, np.uint8)
    lo_, hi_ = np.percentile(nz, 1), np.percentile(nz, 99)
    return np.clip((a - lo_) / max(hi_-lo_, 1) * 255, 0, 255).astype(np.uint8)

mid = len(depths)//2
Image.fromarray(n8(out[mid-3:mid+4].mean(0))).save(OUT + "_mid.png")
# contact sheet across depth
picks = list(range(0, len(depths), max(1, len(depths)//9)))[:9]
th, tw = out.shape[1], out.shape[2]
sheet = Image.new("L", (tw*3, th*3), 0)
for i, d in enumerate(picks):
    sheet.paste(Image.fromarray(n8(out[d])), ((i % 3)*tw, (i//3)*th))
sheet.thumbnail((1500, 1500))
sheet.save(OUT + "_layers.png")
print(f"wrote {OUT}_mid.png and {OUT}_layers.png (layers {picks})")
