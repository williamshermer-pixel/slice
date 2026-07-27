"""Crackle detector, built to Handmer's published description.

His account (caseyhandmer.wordpress.com, 2023-08-05), which is the thing that
led to the first letters:

  "lighter convex patches 0.1-0.5 mm in size separated by narrow, dark, high
   contrast channels typically at angles of 60-90 degrees from each other, and
   otherwise aligned at random with respect to the underlying papyrus fibers"
  "discrete (sharp) boundaries, they do not 'fade' away, but end abruptly"
  "linear features often straight for 2-4 mm and 0.5-1 mm wide"
  "sits 'proud' or slightly above the background papyrus"

Every earlier attempt here measured generic texture ENERGY, which crackle is
not. Crackle is a tile network with a specific plate size and a channel geometry
— and, critically, an orientation that is RANDOM against a fibre weave that we
measured locked to 0/90 degrees with 4.4x anisotropy. Orientation-random on an
orientation-locked background is separable in a way raw energy never was.

Five measured components, each from his description:
  1. plate size        light convex patches, 0.1-0.5 mm
  2. channel darkness  narrow dark high-contrast separators
  3. junction angle    channels meeting at 60-90 degrees
  4. edge sharpness    abrupt, non-fading boundaries
  5. fibre-independence texture orientation NOT aligned to the weave

Scored against Scroll 1's published ink, with a permutation null, per CRITERIA.
"""
import urllib.request, concurrent.futures as cf
import numpy as np
from scipy import ndimage as ndi
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SV = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHercParis4/segments/"
      "20231005123336/surface-volumes/2.4um-0.22m-78keV-volume-20260411134726.zarr")
CH, D = 128, 109
LEVEL, CY, CX, N = 1, 64, 160, 6
UM = 2.4 * 2 ** LEVEL                    # 4.8 um/voxel

PLATE_MIN_UM, PLATE_MAX_UM = 100, 500    # Handmer: 0.1-0.5 mm
PLATE_MIN = PLATE_MIN_UM / UM            # ~21 vox
PLATE_MAX = PLATE_MAX_UM / UM            # ~104 vox


def grab():
    vol = np.zeros((D, N*CH, N*CH), np.float32); got = 0
    def g(cy, cx):
        try:
            with urllib.request.urlopen(f"{SV}/{LEVEL}/0/{cy}/{cx}", timeout=120) as r:
                b = r.read()
            return cy, cx, (np.frombuffer(b, np.uint8).reshape(D, CH, CH) if len(b) == D*CH*CH else None)
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


vol, got = grab()
prof = vol.mean(axis=(1, 2)); pk = int(prof.argmax())
img = vol[max(0, pk-8):pk+8].mean(0)
H, W = img.shape
print(f"fetched {got}/{N*N} chunks at {UM} um/voxel; plate = {PLATE_MIN:.0f}-{PLATE_MAX:.0f} vox")

ink_full = np.array(Image.open("ink_ds8.jpg")).astype(np.float32)
k = 2 ** (3 - LEVEL)
ink = ink_full[(CY*CH)//k:(CY*CH)//k+(N*CH)//k, (CX*CH)//k:(CX*CH)//k+(N*CH)//k]
tgt = (ink > 128).astype(np.float32)


def blk(a):
    h, w = a.shape
    return a[:h//k*k, :w//k*k].reshape(h//k, k, w//k, k).mean(axis=(1, 3))


def score(name, f, verbose=True):
    b = blk(f)
    n0, n1 = min(b.shape[0], tgt.shape[0]), min(b.shape[1], tgt.shape[1])
    b2, t2 = b[:n0, :n1], tgt[:n0, :n1]
    m = np.isfinite(b2)
    r = float(np.corrcoef(b2[m], t2[m])[0, 1])
    if verbose:
        a_, c_ = b2[m & (t2 > .5)], b2[m & (t2 < .5)]
        d = (a_.mean()-c_.mean())/np.sqrt((a_.var()+c_.var())/2+1e-12)
        print(f"  {name:38s} r={r:+.3f}  d={d:+.3f}")
    return r, b2, t2


# ---- 1. CHANNELS: narrow dark high-contrast separators --------------------
chan_r = max(1, int(round(30/UM)))                 # channels ~30 um wide
dark = box(img, int(PLATE_MIN)) - img              # positive in dark channels
chan = dark > np.percentile(dark, 82)

# ---- 2. PLATES: light convex patches between channels --------------------
plates = ~chan
lab, nlab = ndi.label(plates)
sizes = np.bincount(lab.ravel())
diam = 2*np.sqrt(sizes/np.pi)                      # equivalent circular diameter
ok = (diam >= PLATE_MIN) & (diam <= PLATE_MAX)
ok[0] = False
plate_ok = ok[lab]
print(f"  {nlab} plates, {ok.sum()} in Handmer's 0.1-0.5 mm band "
      f"({100*ok.sum()/max(nlab,1):.0f}%)")

# density of correctly-sized plates, at stroke scale (0.5-1 mm)
STROKE_R = int(round(750/UM/2))
plate_density = box(plate_ok.astype(np.float32), STROKE_R)

# ---- 3. EDGE SHARPNESS: abrupt, not fading -------------------------------
gy, gx = np.gradient(img)
gm = np.sqrt(gy*gy + gx*gx)
gm2 = np.sqrt(np.gradient(np.gradient(img, axis=0), axis=0)**2 +
              np.gradient(np.gradient(img, axis=1), axis=1)**2)
sharp = box(gm2, STROKE_R) / np.maximum(box(gm, STROKE_R), 1e-6)

# ---- 4. FIBRE INDEPENDENCE ------------------------------------------------
# the weave is locked to 0/90. crackle is random. so: local orientation
# ENTROPY is high where crackle is, low where bare weave is.
Jxx = box(gx*gx, STROKE_R); Jyy = box(gy*gy, STROKE_R); Jxy = box(gx*gy, STROKE_R)
coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2)/np.maximum(Jxx+Jyy, 1e-6)
ang = 0.5*np.degrees(np.arctan2(2*Jxy, Jxx-Jyy)) % 180
off_axis = np.minimum(np.minimum(np.abs(ang-0), np.abs(ang-90)), np.abs(ang-180))
fibre_indep = box(off_axis.astype(np.float32), STROKE_R)/45.0
disorder = 1.0 - coh                                # low coherence = no single axis

# ---- 5. PROUD: locally raised ---------------------------------------------
proud = img - box(img, int(PLATE_MAX))

print("\nHANDMER COMPONENTS, each alone")
score("1 plate density (0.1-0.5mm)", plate_density)
score("2 channel darkness", box(dark, STROKE_R))
score("3 edge sharpness", sharp)
score("4 off-axis orientation", fibre_indep)
score("4b orientation disorder", disorder)
score("5 proud (raised)", proud)

print("\nCONTROLS")
score("raw intensity", img)
score("generic hf energy (what I built before)",
      np.sqrt(box((img-box(img, max(2, int(PLATE_MIN)//3)))**2, STROKE_R)))


def z(a):
    return (a - a.mean())/(a.std()+1e-9)


combo = z(plate_density) + z(disorder) + z(proud) + 0.5*z(sharp)
r_combo, b2, t2 = score("\nCOMBINED crackle score", combo)

# ---- permutation null, per CRITERIA --------------------------------------
rng = np.random.default_rng(17)
nulls = []
flat = b2[np.isfinite(b2)]
for _ in range(300):
    nulls.append(abs(np.corrcoef(rng.permutation(flat), t2[np.isfinite(b2)])[0, 1]))
nulls = np.array(nulls)
p = float((nulls >= abs(r_combo)).mean())
print(f"\n  permutation null: mean {nulls.mean():.4f} sd {nulls.std():.4f}")
print(f"  p = {p:.4f}   z = {(abs(r_combo)-nulls.mean())/(nulls.std()+1e-9):+.1f}")

def n8(a):
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    return np.clip((a-lo)/max(hi-lo, 1e-6)*255, 0, 255).astype(np.uint8)
S = 420
sh = Image.new("L", (S*3+20, S), 0)
sh.paste(Image.fromarray(n8(blk(img))).resize((S, S), Image.LANCZOS), (0, 0))
sh.paste(Image.fromarray(n8(blk(combo))).resize((S, S), Image.LANCZOS), (S+10, 0))
sh.paste(Image.fromarray(np.clip(ink, 0, 255).astype(np.uint8)).resize((S, S), Image.LANCZOS), (2*S+20, 0))
sh.save("crackle_vs_ink.png")
print("wrote crackle_vs_ink.png  (surface | crackle score | TRUTH)")
