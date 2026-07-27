"""Drive along a sheet. Many small confident walkers instead of one big mesh.

A grown mesh is all-or-nothing: if it sheet-switches once, everything downstream
is wrong and you cannot tell which part. PHerc.1447's best-covered segment turned
out 79% built on nothing, and nothing in its metadata said so.

A swarm is different. Each walker starts somewhere on a bright sheet ridge and
steps along it, re-finding the ridge at every step and stopping the moment it is
no longer confident. A lost walker simply dies. The survivors are short tracks
you can trust, and they can be stitched later.

This is the primitive: one axial slice of an UNREAD scroll, many walkers, each
riding a winding for as far as it honestly can.
"""
import urllib.request, concurrent.futures as cf, sys
import numpy as np
from PIL import Image

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
VOL = "PHerc0800/volumes/20250521135224-8.640um-1.2m-116keV-masked.zarr"
CH = 128
Z = int(sys.argv[1]) if len(sys.argv) > 1 else 11800
CY, CX, N = int(sys.argv[2]) if len(sys.argv) > 2 else 45, int(sys.argv[3]) if len(sys.argv) > 3 else 28, 5


def slice_at(z):
    cz = z // CH; off = z % CH
    out = np.zeros((N*CH, N*CH), np.float32); got = 0
    def g(cy, cx):
        try:
            with urllib.request.urlopen(f"{B}/{VOL}/0/{cz}/{cy}/{cx}", timeout=120) as r:
                b = r.read()
            if len(b) != CH**3: return cy, cx, None
            return cy, cx, np.frombuffer(b, np.uint8).reshape(CH, CH, CH)[off]
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


img, got = slice_at(Z)
H, W = img.shape
print(f"slice z={Z}: {got}/{N*N} chunks, {W} x {H} voxels = {W*8.64/1000:.1f} mm")

# ridge field: sheets are bright lines, so a sheet is where the image is
# brighter than its surroundings
ridge = img - box(img, 6)
ridge[img == 0] = -1e3

# local ridge ORIENTATION via structure tensor of the ridge field. The sheet
# runs perpendicular to the gradient, so that is the direction to drive.
gy, gx = np.gradient(ridge)
Jxx = box(gx*gx, 4); Jyy = box(gy*gy, 4); Jxy = box(gx*gy, 4)
theta = 0.5*np.arctan2(2*Jxy, Jxx - Jyy)        # gradient direction
coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2) / np.maximum(Jxx+Jyy, 1e-6)
# drive along the ridge = perpendicular to the gradient
dirx, diry = -np.sin(theta), np.cos(theta)


def sample(F, y, x):
    yi, xi = int(round(y)), int(round(x))
    if yi < 1 or xi < 1 or yi >= H-1 or xi >= W-1: return None
    return F[yi, xi]


def drive(y, x, sign, max_steps=2000, min_coh=0.25):
    """Ride the ridge until confidence fails. Returns the track."""
    track = [(y, x)]
    vy = vx = None
    for _ in range(max_steps):
        c = sample(coh, y, x)
        r = sample(ridge, y, x)
        if c is None or c < min_coh or r is None or r < 0.5:
            break
        dy, dx = sample(diry, y, x), sample(dirx, y, x)
        if dy is None: break
        # keep going the same way rather than flipping 180 (orientation is
        # defined mod pi, so the sign has to be carried forward by hand)
        if vy is not None and (dy*vy + dx*vx) < 0:
            dy, dx = -dy, -dx
        vy, vx = dy, dx
        ny, nx = y + sign*dy*1.0, x + sign*dx*1.0
        # re-centre onto the ridge crest, perpendicular to travel
        py, px = -dx, dy
        best, bo = None, 0.0
        for o in np.linspace(-2, 2, 9):
            v = sample(ridge, ny + py*o, nx + px*o)
            if v is not None and (best is None or v > best):
                best, bo = v, o
        ny, nx = ny + py*bo, nx + px*bo
        if not (1 <= ny < H-1 and 1 <= nx < W-1): break
        y, x = ny, nx
        track.append((y, x))
    return track


# seeds: the brightest, most coherent ridge points, spread out
cand = []
step = 12
for y in range(10, H-10, step):
    for x in range(10, W-10, step):
        if ridge[y, x] > 3 and coh[y, x] > 0.4:
            cand.append((float(ridge[y, x]), y, x))
cand.sort(reverse=True)
seeds, taken = [], np.zeros((H//step+2, W//step+2), bool)
for _, y, x in cand:
    gy_, gx_ = y//step, x//step
    if taken[gy_, gx_]: continue
    taken[max(0,gy_-1):gy_+2, max(0,gx_-1):gx_+2] = True
    seeds.append((y, x))
    if len(seeds) >= 400: break
print(f"{len(seeds)} seeds")

tracks = []
for (y, x) in seeds:
    t = drive(y, x, +1) + drive(y, x, -1)[::-1]
    if len(t) >= 40:
        tracks.append(t)
lens = np.array([len(t) for t in tracks])
print(f"{len(tracks)} tracks survived >=40 steps")
if lens.size:
    print(f"track length: median {np.median(lens):.0f}  mean {lens.mean():.0f}  "
          f"max {lens.max()} steps ({lens.max()*8.64/1000:.1f} mm)")
    print(f"total traced: {lens.sum()*8.64/1000:.0f} mm of sheet in one slice")

# render
def n8(a):
    nz = a[a > 0]
    lo, hi = np.percentile(nz, 1), np.percentile(nz, 99)
    return np.clip((a-lo)/max(hi-lo, 1)*255, 0, 255).astype(np.uint8)
rgb = np.dstack([n8(img)]*3)
for i, t in enumerate(tracks):
    col = [(200, 150, 30), (60, 200, 220), (220, 90, 90), (150, 220, 120)][i % 4]
    for (y, x) in t:
        yi, xi = int(y), int(x)
        if 0 <= yi < H and 0 <= xi < W:
            rgb[yi, xi] = col
Image.fromarray(rgb).save("drive_tracks.png")
Image.fromarray(n8(img)).save("drive_slice.png")
print("wrote drive_tracks.png (traces over the slice) and drive_slice.png")
