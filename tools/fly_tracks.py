"""Fly the combed tracks. Orbit + a dolly along the longest one.

A plain 3D projector: rotate the point cloud, project, shade by depth. No
dependencies beyond numpy and PIL, so it runs anywhere the combing runs.

Depth shading is the point — it is what tells you whether the swarm is riding a
set of nested surfaces or just making a haystack.
"""
import csv, math
from collections import defaultdict
import numpy as np
from PIL import Image

CSV = "tracks.csv"
W = H = 900

tracks = defaultdict(list)
with open(CSV) as f:
    for row in csv.DictReader(f):
        tracks[int(row["track"])].append(
            (float(row["x_mm"]), float(row["y_mm"]), float(row["z_mm"])))
ids = sorted(tracks, key=lambda k: -len(tracks[k]))
print(f"{len(ids)} tracks, {sum(len(v) for v in tracks.values()):,} points")

P, T = [], []
for tid in ids:
    for p in tracks[tid]:
        P.append(p); T.append(tid)
P = np.array(P, np.float32); T = np.array(T)
C = P.mean(0); P -= C
scale = np.percentile(np.abs(P), 99)
P /= scale
print(f"extent after centring: {P.min(0).round(2)} .. {P.max(0).round(2)}")

# stable per-track hue so a single sheet keeps one colour as it rotates
rng = np.random.default_rng(3)
hue = rng.random(len(ids))
tid2i = {t: i for i, t in enumerate(ids)}
HU = np.array([hue[tid2i[t]] for t in T], np.float32)


def hsv(h, s, v):
    i = (h*6).astype(int) % 6
    f = h*6 - (h*6).astype(int)
    p, q, t = v*(1-s), v*(1-s*f), v*(1-s*(1-f))
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [v, q, p, p, t, v])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [t, v, v, q, p, p])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [p, p, q, v, v, t])
    return r, g, b


def render(yaw, pitch, zoom=1.0, dolly=None):
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    X = x*cy + z*sy
    Z = -x*sy + z*cy
    Y = y*cp - Z*sp
    Zr = y*sp + Z*cp
    if dolly is not None:
        X = X - dolly[0]; Y = Y - dolly[1]; Zr = Zr - dolly[2]
    d = Zr
    dn = (d - d.min())/max(d.max()-d.min(), 1e-6)
    px = ((X*zoom*0.42 + 0.5)*W).astype(int)
    py = ((-Y*zoom*0.42 + 0.5)*H).astype(int)
    ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
    order = np.argsort(-d[ok])          # far first so near overwrites
    pxo, pyo, dno, huo = px[ok][order], py[ok][order], dn[ok][order], HU[ok][order]
    val = 0.30 + 0.70*(1-dno)
    r, g, b = hsv(huo, 0.55, val)
    img = np.zeros((H, W, 3), np.float32)
    idx = pyo*W + pxo
    flat = img.reshape(-1, 3)
    flat[idx, 0] = r; flat[idx, 1] = g; flat[idx, 2] = b
    return Image.fromarray((np.clip(img, 0, 1)*255).astype(np.uint8))


frames = []
NF = 36
for k in range(NF):
    yaw = 2*math.pi*k/NF
    frames.append(render(yaw, math.radians(18), zoom=1.15))
    if k % 9 == 0: print(f"  orbit frame {k+1}/{NF}")
frames[0].save("fly_orbit.gif", save_all=True, append_images=frames[1:],
               duration=70, loop=0, optimize=True)
print("wrote fly_orbit.gif")

# a few stills at telling angles
for name, (yaw, pitch, zoom) in {
    "fly_side":  (0.0, math.radians(2), 1.5),          # edge on: nested windings
    "fly_down":  (0.0, math.radians(88), 1.15),        # from above: the spiral
    "fly_three": (math.radians(35), math.radians(25), 1.3),
}.items():
    render(yaw, pitch, zoom).save(f"{name}.png")
    print(f"wrote {name}.png")
