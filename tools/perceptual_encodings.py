"""Glasses: push the weak signal into channels the eye is actually good at.

Adds no information. r=0.2 stays r=0.2. What it changes is which part of the
visual system gets to look at it — and the precedent matters: the "crackle" that
won the 2023 Grand Prize was found by a person looking at pictures, not by a
detector.

Three encodings:

  ANAGLYPH   the feature becomes horizontal disparity between the red and cyan
             channels, so it reads as depth through red/cyan glasses. Stereopsis
             resolves differences far below conscious brightness discrimination.

  BLINK      two frames alternating — Tombaugh's comparator, which found Pluto.
             The eye detects change vastly better than absolute difference.

  OPPONENT   signal on the red-green axis at constant luminance. Colour
             opponency fires where a luminance ramp does nothing.

Ground truth is rendered alongside every output so nothing here can be admired
without immediately being checked against the answer.
"""
import urllib.request, concurrent.futures as cf
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SV = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHercParis4/segments/"
      "20231005123336/surface-volumes/2.4um-0.22m-78keV-volume-20260411134726.zarr")
CH, D = 128, 109
LEVEL, CY, CX, N = 1, 64, 160, 6
UM = 2.4 * 2 ** LEVEL


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


def norm(a, lo=1, hi=99):
    m = np.isfinite(a)
    l, h = np.percentile(a[m], lo), np.percentile(a[m], hi)
    return np.clip((a - l) / max(h - l, 1e-6), 0, 1)


vol, got = grab()
H, W = vol.shape[1], vol.shape[2]
print(f"fetched {got}/{N*N} chunks, {UM} um/voxel")
prof = vol.mean(axis=(1, 2)); pk = int(prof.argmax())
STROKE = int(round(346/UM))

img = vol[max(0, pk-8):pk+8].mean(0)
hp = img - box(img, max(2, STROKE//3))
feat = np.sqrt(box(hp*hp, STROKE))                 # the strongest feature we have
feat = norm(feat)
base = norm(img)

ink_full = np.array(Image.open("ink_ds8.jpg")).astype(np.float32)
k = 2 ** (3 - LEVEL)
ink = ink_full[(CY*CH)//k:(CY*CH)//k + (N*CH)//k, (CX*CH)//k:(CX*CH)//k + (N*CH)//k]
ink_up = np.array(Image.fromarray(ink.astype(np.uint8)).resize((W, H), Image.NEAREST))

# ---------------- ANAGLYPH -------------------------------------------------
# shift red and cyan in opposite directions BY the feature, so strong feature
# = large disparity = pops forward through the glasses
MAXSHIFT = 6
xs = np.arange(W)[None, :].repeat(H, 0)
d = (feat * MAXSHIFT).astype(int)
rx = np.clip(xs - d, 0, W-1)
cx_ = np.clip(xs + d, 0, W-1)
ys = np.arange(H)[:, None].repeat(W, 1)
red = base[ys, rx]
cyan = base[ys, cx_]
ana = np.dstack([red, cyan, cyan])
Image.fromarray((ana*255).astype(np.uint8)).save("glasses_anaglyph.png")
print("wrote glasses_anaglyph.png   (red/cyan glasses: raised = toward you)")

# ---------------- BLINK ----------------------------------------------------
# frame A: plain surface.  frame B: surface with the feature pushed hard.
# the eye catches what moves between them.
a = np.dstack([base]*3)
b = np.dstack([np.clip(base + 0.55*(feat-feat.mean()), 0, 1)]*3)
fr = [Image.fromarray((x*255).astype(np.uint8)) for x in (a, b)]
fr[0].save("glasses_blink.gif", save_all=True, append_images=fr[1:],
           duration=420, loop=0)
print("wrote glasses_blink.gif      (Tombaugh comparator: watch what flickers)")

# ---------------- OPPONENT -------------------------------------------------
# constant luminance, signal on red-green only
g = feat - feat.mean()
opp = np.dstack([np.clip(0.5+g, 0, 1), np.clip(0.5-g, 0, 1), np.full_like(g, 0.5)])
Image.fromarray((opp*255).astype(np.uint8)).save("glasses_opponent.png")
print("wrote glasses_opponent.png   (red/green axis at flat luminance)")

# ---------------- the honest check ----------------------------------------
S = 430
sheet = Image.new("RGB", (S*3+20, S), (10, 10, 10))
sheet.paste(Image.fromarray((np.dstack([base]*3)*255).astype(np.uint8)).resize((S, S), Image.LANCZOS), (0, 0))
sheet.paste(Image.fromarray((opp*255).astype(np.uint8)).resize((S, S), Image.LANCZOS), (S+10, 0))
sheet.paste(Image.fromarray(np.dstack([ink_up]*3).astype(np.uint8)).resize((S, S), Image.LANCZOS), (2*S+20, 0))
sheet.save("glasses_vs_truth.png")
print("wrote glasses_vs_truth.png   (plain | opponent | GROUND TRUTH)")
print(f"\nregion is {W*UM/1000:.1f} mm across; a letter is {3000/UM:.0f} voxels tall")
print("if the encodings are working you should see the same shapes as panel 3.")
