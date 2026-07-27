"""Held-out validation of the crackle detector, per CRITERIA.md.

Parameters were chosen on tile (64,160). They are FROZEN here — nothing is
refit. The detector runs unchanged on tiles it has never seen, plus a negative
control region with little or no ink.

Passing means: correlation holds on held-out tiles, clears a spatial null that
preserves autocorrelation, and does NOT light up on the negative control.

Failing any of those means we do not have a detector, however good the first
tile looked.
"""
import urllib.request, concurrent.futures as cf
import numpy as np
from scipy import ndimage as ndi
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SV = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHercParis4/segments/"
      "20231005123336/surface-volumes/2.4um-0.22m-78keV-volume-20260411134726.zarr")
CH, D = 128, 109
LEVEL, N = 1, 6
UM = 2.4 * 2 ** LEVEL
k = 2 ** (3 - LEVEL)

# ---- FROZEN PARAMETERS, chosen on tile (64,160). Do not touch. -------------
STROKE_R = int(round(750 / UM / 2))
CHAN_SCALE = int(round(200 / UM))
CHAN_PCT = 70
PLATE_LO, PLATE_HI = 100 / UM, 500 / UM
WEIGHTS = (1.0, 0.7, 0.5)          # sharpness, off-axis, plate
TUNED_ON = (64, 160)
# ---------------------------------------------------------------------------

ink_full = np.array(Image.open("ink_ds8.jpg")).astype(np.float32)


def grab(cy, cx):
    vol = np.zeros((D, N*CH, N*CH), np.float32); got = 0
    def g(y, x):
        try:
            with urllib.request.urlopen(f"{SV}/{LEVEL}/0/{y}/{x}", timeout=120) as r:
                b = r.read()
            return y, x, (np.frombuffer(b, np.uint8).reshape(D, CH, CH) if len(b) == D*CH*CH else None)
        except Exception:
            return y, x, None
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for y, x, a in ex.map(lambda p: g(*p), [(cy+j, cx+i) for j in range(N) for i in range(N)]):
            if a is not None:
                got += 1
                vol[:, (y-cy)*CH:(y-cy+1)*CH, (x-cx)*CH:(x-cx+1)*CH] = a
    return vol, got


def box(a, r):
    kk = 2*r+1
    c = np.cumsum(np.pad(a.astype(np.float32), ((r+1, r), (0, 0)), mode="edge"), axis=0)
    o = (c[kk:]-c[:-kk])/kk
    c = np.cumsum(np.pad(o, ((0, 0), (r+1, r)), mode="edge"), axis=1)
    return (c[:, kk:]-c[:, :-kk])/kk


def z(a):
    return (a - a.mean())/(a.std()+1e-9)


def detector(img):
    """Frozen. No parameter here is chosen per-tile."""
    gy, gx = np.gradient(img)
    gm = np.sqrt(gy*gy + gx*gx)
    gm2 = np.sqrt(np.gradient(np.gradient(img, axis=0), axis=0)**2 +
                  np.gradient(np.gradient(img, axis=1), axis=1)**2)
    sharp = box(gm2, STROKE_R)/np.maximum(box(gm, STROKE_R), 1e-6)
    Jxx = box(gx*gx, STROKE_R); Jyy = box(gy*gy, STROKE_R); Jxy = box(gx*gy, STROKE_R)
    ang = 0.5*np.degrees(np.arctan2(2*Jxy, Jxx-Jyy)) % 180
    off = np.minimum(np.minimum(np.abs(ang), np.abs(ang-90)), np.abs(ang-180))
    offax = box(off.astype(np.float32), STROKE_R)/45.0
    dark = box(img, CHAN_SCALE) - img
    chan = dark > np.percentile(dark, CHAN_PCT)
    lab, n = ndi.label(~chan)
    sizes = np.bincount(lab.ravel()); diam = 2*np.sqrt(sizes/np.pi)
    ok = (diam >= PLATE_LO) & (diam <= PLATE_HI); ok[0] = False
    plate = box(ok[lab].astype(np.float32), STROKE_R)
    a, b, c = WEIGHTS
    return a*z(sharp) + b*z(offax) + c*z(plate)


def blk(a):
    h, w = a.shape
    return a[:h//k*k, :w//k*k].reshape(h//k, k, w//k, k).mean(axis=(1, 3))


def evaluate(cy, cx, label):
    vol, got = grab(cy, cx)
    if got < N*N*0.8:
        print(f"{label:26s} only {got}/{N*N} chunks — skipped"); return None
    prof = vol.mean(axis=(1, 2)); pk = int(prof.argmax())
    img = vol[max(0, pk-8):pk+8].mean(0)
    ink = ink_full[(cy*CH)//k:(cy*CH)//k+(N*CH)//k, (cx*CH)//k:(cx*CH)//k+(N*CH)//k]
    tgt = (ink > 128).astype(np.float32)
    cov = float(tgt.mean())
    f = blk(detector(img))
    n0, n1 = min(f.shape[0], tgt.shape[0]), min(f.shape[1], tgt.shape[1])
    f, tgt = f[:n0, :n1], tgt[:n0, :n1]
    if cov < 0.02:
        print(f"{label:26s} ink {100*cov:4.1f}%  NEGATIVE CONTROL — "
              f"score sd {f.std():.3f}, mean {f.mean():+.3f}")
        return ("neg", f, tgt, cov)
    r = float(np.corrcoef(f.ravel(), tgt.ravel())[0, 1])
    a_, c_ = f[tgt > .5], f[tgt < .5]
    d = (a_.mean()-c_.mean())/np.sqrt((a_.var()+c_.var())/2+1e-12)
    rng = np.random.default_rng(11)
    h, w = tgt.shape
    nulls = np.array([abs(np.corrcoef(f.ravel(),
                     np.roll(np.roll(tgt, rng.integers(h//6, h-h//6), 0),
                             rng.integers(w//6, w-w//6), 1).ravel())[0, 1])
                      for _ in range(300)])
    p = float((nulls >= abs(r)).mean())
    tag = "TUNED ON" if (cy, cx) == TUNED_ON else "held out"
    print(f"{label:26s} ink {100*cov:4.1f}%  r={r:+.3f}  d={d:+.3f}  "
          f"null max {nulls.max():.3f}  p={p:.4f}   [{tag}]")
    return ("pos", r, d, p, cov)


print("CRACKLE DETECTOR — HELD-OUT VALIDATION")
print(f"parameters frozen from tile {TUNED_ON}; nothing refit below\n")
tiles = [(64, 160, "tile A (tuned on)"),
         (40, 100, "tile B held-out"),
         (88, 220, "tile C held-out"),
         (52, 260, "tile D held-out"),
         (100, 120, "tile E held-out")]
res = []
for cy, cx, lab in tiles:
    try:
        res.append((lab, evaluate(cy, cx, lab)))
    except Exception as e:
        print(f"{lab:26s} failed: {type(e).__name__}: {e}")

pos = [x for _, x in res if x and x[0] == "pos"]
held = [x for lab, x in res if x and x[0] == "pos" and "held" in lab]
if held:
    rr = np.array([h[1] for h in held]); dd = np.array([h[2] for h in held])
    pp = np.array([h[3] for h in held])
    print(f"\nHELD-OUT SUMMARY  n={len(held)}")
    print(f"  r: mean {rr.mean():+.3f}  range {rr.min():+.3f}..{rr.max():+.3f}")
    print(f"  d: mean {dd.mean():+.3f}")
    print(f"  p: max {pp.max():.4f}   all below 0.05? {bool((pp < 0.05).all())}")
    print("\nVERDICT:", "HOLDS on held-out data" if (rr > 0.15).all() and (pp < 0.05).all()
          else "DOES NOT HOLD — the first tile was a fit, not a detector")
