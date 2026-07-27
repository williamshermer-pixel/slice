"""Does the CRACK NETWORK differ inside letters?

Mechanism under test: the ink was already carbon before the eruption and did not
pyrolyse. The papyrus did, and shrank. A non-shrinking film bonded to a
shrinking substrate cracks — like glaze crazing. If that is what happened, the
crack pattern should differ where ink is, and the difference is GEOMETRY (crack
density, spacing, orientation, branching) rather than brightness.

Geometry is the interesting part: cracks run for hundreds of microns, so they
survive coarse sampling in a way a 15 um film does not.

Ground truth is the published ink map for Scroll 1. Everything is measured
inside ink vs outside, on the same tile, at the same time.
"""
import urllib.request, concurrent.futures as cf
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SV = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHercParis4/segments/"
      "20231005123336/surface-volumes/2.4um-0.22m-78keV-volume-20260411134726.zarr")
CH, D = 128, 109
LEVEL, CY, CX, N = 1, 64, 160, 6      # 4.8 um/voxel, 768x768
UM = 2.4 * (2 ** LEVEL)


def band(zlo, zhi):
    out = np.zeros((N * CH, N * CH), np.float32); got = 0
    def g(cy, cx):
        try:
            with urllib.request.urlopen(f"{SV}/{LEVEL}/0/{cy}/{cx}", timeout=120) as r:
                b = r.read()
            if len(b) != D * CH * CH: return cy, cx, None
            return cy, cx, np.frombuffer(b, np.uint8).reshape(D, CH, CH)[zlo:zhi].mean(0)
        except Exception:
            return cy, cx, None
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for cy, cx, a in ex.map(lambda p: g(*p), [(CY+j, CX+i) for j in range(N) for i in range(N)]):
            if a is not None:
                got += 1
                out[(cy-CY)*CH:(cy-CY+1)*CH, (cx-CX)*CH:(cx-CX+1)*CH] = a
    return out, got


def box(a, r):
    k = 2*r+1
    c = np.cumsum(np.pad(a.astype(np.float32), ((r+1, r), (0, 0)), mode="edge"), axis=0)
    o = (c[k:]-c[:-k])/k
    c = np.cumsum(np.pad(o, ((0, 0), (r+1, r)), mode="edge"), axis=1)
    return (c[:, k:]-c[:, :-k])/k


img, got = band(45, 70)
H, W = img.shape
print(f"fetched {got}/{N*N} chunks, {UM} um/voxel, {W*UM/1000:.1f} mm across")

ink_full = np.array(Image.open("ink_ds8.jpg")).astype(np.float32)
k = 2 ** (3 - LEVEL)
ink = ink_full[(CY*CH)//k:(CY*CH)//k + (N*CH)//k, (CX*CH)//k:(CX*CH)//k + (N*CH)//k]


def blk(a):
    h, w = a.shape
    return a[:h//k*k, :w//k*k].reshape(h//k, k, w//k, k).mean(axis=(1, 3))


# --- crack detection: cracks are thin DARK valleys, so find local minima
# relative to a neighbourhood a bit wider than a crack.
CRACK_R = max(2, int(round(40 / UM)))          # cracks ~40 um wide
bg = box(img, CRACK_R * 3)
valley = bg - img                               # positive where darker than around
thr = np.percentile(valley[img > 0], 88)
crack = (valley > thr) & (img > 0)
print(f"crack mask: {100*crack.mean():.1f}% of voxels (threshold {thr:.2f})")

# --- crack ORIENTATION via structure tensor of the crack field
gy, gx = np.gradient(valley)
Jxx = box(gx*gx, CRACK_R*2); Jyy = box(gy*gy, CRACK_R*2); Jxy = box(gx*gy, CRACK_R*2)
coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2) / np.maximum(Jxx+Jyy, 1e-6)
ang = 0.5*np.degrees(np.arctan2(2*Jxy, Jxx-Jyy)) % 180

# --- aggregate to the ink grid and split
dens = blk(crack.astype(np.float32))
cohb = blk(coh)
n0, n1 = min(dens.shape[0], ink.shape[0]), min(dens.shape[1], ink.shape[1])
dens, cohb, ink = dens[:n0, :n1], cohb[:n0, :n1], ink[:n0, :n1]
A = ink > 150      # under ink
Bm = ink < 50      # bare
print(f"ink {100*A.mean():.1f}%   bare {100*Bm.mean():.1f}%\n")


def cmp(name, f, unit=""):
    a, b = f[A], f[Bm]
    if a.size < 200 or b.size < 200:
        print(f"  {name:28s} too few samples"); return
    d = (a.mean()-b.mean())/np.sqrt((a.var()+b.var())/2 + 1e-12)
    r = float(np.corrcoef(f.ravel(), A.ravel().astype(float))[0, 1])
    print(f"  {name:28s} ink {a.mean():8.4f}{unit}  bare {b.mean():8.4f}{unit}  "
          f"ratio {a.mean()/max(b.mean(),1e-9):5.3f}  d={d:+.3f}  r={r:+.3f}")


print("CRACK GEOMETRY, inside letters vs outside")
cmp("crack density", dens)
cmp("crack orientation coherence", cohb)

# spacing: distance between cracks along rows, measured separately in each class
def spacing(mask_region):
    gaps = []
    for y in range(0, H, 4):
        row = crack[y]
        idx = np.flatnonzero(row)
        if idx.size > 2:
            gaps.extend(np.diff(idx).tolist())
    return np.array(gaps)


# branching proxy: crack pixels with >2 crack neighbours
nb = np.zeros_like(crack, np.uint8)
for dy in (-1, 0, 1):
    for dx in (-1, 0, 1):
        if dy == 0 and dx == 0: continue
        nb[1:-1, 1:-1] += crack[1+dy:H-1+dy, 1+dx:W-1+dx].astype(np.uint8)
branch = blk(((nb > 2) & crack).astype(np.float32))[:n0, :n1]
cmp("crack branch points", branch)

# and the control we already know fails
cmp("raw brightness (control)", blk(img)[:n0, :n1])

print("\nreading: |d| < 0.2 is negligible; the brightness control sits near d=0.2")
