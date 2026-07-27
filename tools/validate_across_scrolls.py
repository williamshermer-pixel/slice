"""Validation harness: run the frozen detector across every published ink detection.

Everything in this session was validated on ONE segment of ONE scroll. That is
how a detector scored r=+0.368 on the tile it was tuned on and -0.062 on held-out
tiles of the same sheet. The bucket turns out to hold 255 segments with published
ink detections across seven scrolls — different scribes, scans, and damage
states.

This harness:
  1. finds every segment with an ink detection AND a surface volume
  2. runs the FROZEN detector on each, unchanged
  3. reports the DISTRIBUTION of correlations, not one number
  4. runs a spatial null per segment (shifted target, autocorrelation preserved)

A real effect survives across scribes and scans. A fit to one sheet's damage
does not. The distribution is the answer either way — a median near zero is a
result, not a failure.

Nothing here refits anything. Parameters are literally copied from the tile they
were chosen on and never touched again.
"""
import urllib.request, urllib.parse, concurrent.futures as cf, io, json, sys, time
import numpy as np
from scipy import ndimage as ndi
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH = 128
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 60
WORKERS = 10


def get(u, t=90):
    return urllib.request.urlopen(u, timeout=t).read()


def listing(prefix, delim=True):
    out, tok = [], None
    for _ in range(12):
        u = f"{B}?list-type=2&prefix={urllib.parse.quote(prefix)}"
        if delim:
            u += "&delimiter=/"
        if tok:
            u += "&continuation-token=" + urllib.parse.quote(tok)
        try:
            xml = get(u, 45).decode()
        except Exception:
            return out
        tag = "<Prefix>" if delim else "<Key>"
        end = "</Prefix>" if delim else "</Key>"
        for part in xml.split(tag)[1:]:
            v = part.split(end)[0]
            if v != prefix:
                out.append(v)
        if "<IsTruncated>true</IsTruncated>" in xml:
            tok = xml.split("<NextContinuationToken>")[1].split("</Next")[0]
        else:
            break
    return out


# ---------------- FROZEN DETECTOR -----------------------------------------
# Parameters chosen on PHercParis4/20231005123336 tile (64,160) at 4.8 um/voxel.
# Scales are expressed in MICRONS so they transfer across scans of different
# voxel size — that is the one concession to portability, and it is not a refit.
STROKE_UM, CHAN_UM = 750, 200
PLATE_LO_UM, PLATE_HI_UM = 100, 500
CHAN_PCT = 70
WEIGHTS = (1.0, 0.7, 0.5)


def box(a, r):
    r = max(1, int(r)); k = 2*r+1
    c = np.cumsum(np.pad(a.astype(np.float32), ((r+1, r), (0, 0)), mode="edge"), axis=0)
    o = (c[k:]-c[:-k])/k
    c = np.cumsum(np.pad(o, ((0, 0), (r+1, r)), mode="edge"), axis=1)
    return (c[:, k:]-c[:, :-k])/k


def z(a):
    return (a - a.mean())/(a.std()+1e-9)


def detector(img, um):
    sr = max(2, int(round(STROKE_UM/um/2)))
    gy, gx = np.gradient(img)
    gm = np.sqrt(gy*gy+gx*gx)
    gm2 = np.sqrt(np.gradient(np.gradient(img, axis=0), axis=0)**2 +
                  np.gradient(np.gradient(img, axis=1), axis=1)**2)
    sharp = box(gm2, sr)/np.maximum(box(gm, sr), 1e-6)
    Jxx = box(gx*gx, sr); Jyy = box(gy*gy, sr); Jxy = box(gx*gy, sr)
    ang = 0.5*np.degrees(np.arctan2(2*Jxy, Jxx-Jyy)) % 180
    off = np.minimum(np.minimum(np.abs(ang), np.abs(ang-90)), np.abs(ang-180))
    offax = box(off.astype(np.float32), sr)/45.0
    dark = box(img, max(1, int(round(CHAN_UM/um)))) - img
    chan = dark > np.percentile(dark, CHAN_PCT)
    lab, _ = ndi.label(~chan)
    sizes = np.bincount(lab.ravel()); diam = 2*np.sqrt(sizes/np.pi)
    ok = (diam >= PLATE_LO_UM/um) & (diam <= PLATE_HI_UM/um); ok[0] = False
    plate = box(ok[lab].astype(np.float32), sr)
    a, b, c = WEIGHTS
    return a*z(sharp) + b*z(offax) + c*z(plate)
# ---------------------------------------------------------------------------


def find_targets():
    samples = [p.rstrip("/") for p in listing("") if p.startswith("PHerc")]
    segs = []
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for s, r in zip(samples, ex.map(lambda s: listing(f"{s}/segments/"), samples)):
            segs += r
    def probe(seg):
        ink = [k for k in listing(seg+"ink-detection/downsampled/", delim=False)
               if k.lower().endswith((".jpg", ".png"))]
        if not ink:
            return None
        sv = [p for p in listing(seg+"surface-volumes/") if p.endswith(".zarr/")]
        if not sv:
            return None
        return dict(seg=seg, ink=ink[0], sv=sv)
    out = []
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        for r in ex.map(probe, segs):
            if r:
                out.append(r)
    return out


def voxel_um(name):
    import re
    m = re.search(r"(\d+\.?\d*)um", name)
    return float(m.group(1)) if m else None


def evaluate(t):
    seg = t["seg"]
    try:
        ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}", 120)))).astype(np.float32)
        if ink.ndim == 3:
            ink = ink.mean(2)
        if min(ink.shape) < 200:
            return dict(seg=seg, err="ink preview too small")
        cov = float((ink > 128).mean())
        if not (0.03 < cov < 0.75):
            return dict(seg=seg, err=f"ink coverage {100*cov:.0f}%")

        # pick the finest surface volume available
        best = None
        for sv in t["sv"]:
            um = voxel_um(sv.rstrip("/").split("/")[-1])
            if um and (best is None or um < best[0]):
                best = (um, sv)
        if not best:
            return dict(seg=seg, err="no voxel size in name")
        um, sv = best

        za = json.loads(get(f"{B}/{sv}0/.zarray", 60).decode())
        D, HH, WW = za["shape"]
        cz = za["chunks"]
        if cz[1] != CH:
            return dict(seg=seg, err=f"chunk {cz}")

        # the ink preview is a downsample of the sheet; work out by how much
        ds = WW / ink.shape[1]
        if not (1.5 < ds < 40):
            return dict(seg=seg, err=f"odd downsample {ds:.1f}")

        # a 4x4 chunk tile from the middle of the sheet
        cy0, cx0 = (HH//CH)//2 - 2, (WW//CH)//2 - 2
        if cy0 < 0 or cx0 < 0:
            return dict(seg=seg, err="sheet too small")
        NT = 4
        vol = np.zeros((D, NT*CH, NT*CH), np.float32); got = 0
        def g(cy, cx):
            try:
                b = get(f"{B}/{sv}0/0/{cy}/{cx}", 120)
                need = D*CH*CH
                return cy, cx, (np.frombuffer(b, np.uint8).reshape(D, CH, CH)
                                if len(b) == need else None)
            except Exception:
                return cy, cx, None
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for cy, cx, a in ex.map(lambda p: g(*p),
                                    [(cy0+j, cx0+i) for j in range(NT) for i in range(NT)]):
                if a is not None:
                    got += 1
                    vol[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
        if got < NT*NT*0.75:
            return dict(seg=seg, err=f"chunks {got}/{NT*NT}")

        prof = vol.mean(axis=(1, 2)); pk = int(prof.argmax())
        img = vol[max(0, pk-6):pk+7].mean(0)
        if (img > 0).mean() < 0.5:
            return dict(seg=seg, err="tile mostly empty")

        f = detector(img, um)
        # aggregate detector to the ink preview grid
        step = max(1, int(round(ds)))
        h, w = f.shape
        fb = f[:h//step*step, :w//step*step].reshape(h//step, step, w//step, step).mean(axis=(1, 3))
        iy, ix = int(cy0*CH/ds), int(cx0*CH/ds)
        sub = ink[iy:iy+fb.shape[0], ix:ix+fb.shape[1]]
        n0, n1 = min(fb.shape[0], sub.shape[0]), min(fb.shape[1], sub.shape[1])
        if n0 < 24 or n1 < 24:
            return dict(seg=seg, err="overlap too small")
        fb, sub = fb[:n0, :n1], sub[:n0, :n1]
        tg = (sub > 128).astype(np.float32)
        c = float(tg.mean())
        if not (0.03 < c < 0.9):
            return dict(seg=seg, err=f"tile ink {100*c:.0f}%")
        r = float(np.corrcoef(fb.ravel(), tg.ravel())[0, 1])
        rng = np.random.default_rng(3)
        nulls = np.array([abs(np.corrcoef(fb.ravel(),
                          np.roll(np.roll(tg, rng.integers(6, n0-6), 0),
                                  rng.integers(6, n1-6), 1).ravel())[0, 1])
                          for _ in range(120)])
        return dict(seg=seg, um=um, r=r, p=float((nulls >= abs(r)).mean()),
                    nullmax=float(nulls.max()), cov=c)
    except Exception as e:
        return dict(seg=seg, err=f"{type(e).__name__}")


t0 = time.time()
print("finding segments with ink detection AND surface volumes …")
targets = find_targets()
print(f"{len(targets)} usable segments; testing {min(LIMIT, len(targets))}\n")
targets = targets[:LIMIT]

rows, errs = [], {}
done = 0
with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for res in ex.map(evaluate, targets):
        done += 1
        if "err" in res:
            errs[res["err"]] = errs.get(res["err"], 0)+1
        else:
            rows.append(res)
            s = res["seg"].split("/")[0] + "/" + res["seg"].split("/")[-2][:26]
            print(f"  {s:48s} {res['um']:5.2f}um  r={res['r']:+.3f}  p={res['p']:.3f}")
        if done % 10 == 0:
            print(f"    … {done}/{len(targets)}  ({time.time()-t0:.0f}s)", flush=True)

print(f"\n=== {len(rows)} segments evaluated in {time.time()-t0:.0f}s ===")
if errs:
    print("skipped:", dict(sorted(errs.items(), key=lambda kv: -kv[1])[:6]))
if rows:
    r = np.array([x["r"] for x in rows]); p = np.array([x["p"] for x in rows])
    scrolls = {}
    for x in rows:
        scrolls.setdefault(x["seg"].split("/")[0], []).append(x["r"])
    print(f"\nr across all segments: median {np.median(r):+.3f}  mean {r.mean():+.3f}  "
          f"sd {r.std():.3f}  range {r.min():+.3f}..{r.max():+.3f}")
    print(f"fraction with r > 0.15 : {100*(r > 0.15).mean():.0f}%")
    print(f"fraction with p < 0.05 : {100*(p < 0.05).mean():.0f}%")
    print("\nby scroll:")
    for s, v in sorted(scrolls.items()):
        v = np.array(v)
        print(f"  {s:16s} n={len(v):3d}  median r={np.median(v):+.3f}")
    json.dump(rows, open("harness_results.json", "w"), indent=1)
    print("\nwrote harness_results.json")
    print("\nVERDICT:", "GENERALISES" if np.median(r) > 0.15 and (p < 0.05).mean() > 0.5
          else "DOES NOT GENERALISE — it was fitting one sheet")
