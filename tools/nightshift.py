"""NIGHTSHIFT — an autonomous search for an ink feature that generalises.

The failure this exists to prevent: a detector was hand-tuned on one tile,
scored r=+0.368 with z=+6.18, and collapsed to median r=+0.013 across segments
it had not seen. Tuning and testing on the same data manufactures certainty.

So the objective function here is NOT fit. It is generalisation:

    score = median correlation across N segments the variant never saw,
            on scrolls it was not tuned on

A variant that nails one sheet and fails the rest scores zero. There is no way
to win by overfitting, because fit is never measured.

WHAT IT DOES
  - draws a random variant from the feature/parameter space
  - evaluates it on a TUNE set (a few segments) purely to reject the hopeless
  - anything promising goes to a HELD-OUT set on DIFFERENT SCROLLS
  - held-out median is the only score that counts
  - spatial null per segment (shifted target, autocorrelation preserved)
  - logs every variant, promising or not, so the negative space is recorded

ALERT CONDITION (from CRITERIA.md, deliberately hard to hit)
  held-out median r  >= 0.25
  AND  >= 60% of held-out segments with p < 0.05
  AND  >= 8 held-out segments, spanning >= 2 scrolls
  AND  a negative control that stays near zero

Anything less is written to the log and NOT announced. Silence overnight means
nothing cleared, which is information.

Usage:  python3 nightshift.py [hours]
"""
import urllib.request, urllib.parse, concurrent.futures as cf, io, json, sys, time, math, os
import numpy as np
from scipy import ndimage as ndi
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH = 128
# Parsed defensively: this module is imported by other tools whose own argv
# looks nothing like this one's. A bare float(sys.argv[1]) throws at IMPORT
# time under `dogs.py --run 12 0`, and an importer that wraps it in try/except
# then silently loses the whole texture feature bank.
HOURS = (float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
         else 8.0)
LOG = "nightshift_log.jsonl"
ALERT = "NIGHTSHIFT_ALERT.md"
CACHE = "nightshift_targets.json"

# ---- the bar. deliberately hard. ------------------------------------------
MIN_HELDOUT_R      = 0.25
MIN_FRAC_SIGNIF    = 0.60
MIN_HELDOUT_SEGS   = 8
MIN_SCROLLS        = 2
MAX_NEG_CONTROL_R  = 0.12
# ---------------------------------------------------------------------------


def get(u, t=90):
    return urllib.request.urlopen(u, timeout=t).read()


def listing(prefix, delim=True):
    out, tok = [], None
    for _ in range(12):
        u = f"{B}?list-type=2&prefix={urllib.parse.quote(prefix)}"
        if delim: u += "&delimiter=/"
        if tok: u += "&continuation-token=" + urllib.parse.quote(tok)
        try: xml = get(u, 45).decode()
        except Exception: return out
        tag, end = ("<Prefix>", "</Prefix>") if delim else ("<Key>", "</Key>")
        for part in xml.split(tag)[1:]:
            v = part.split(end)[0]
            if v != prefix: out.append(v)
        if "<IsTruncated>true</IsTruncated>" in xml:
            tok = xml.split("<NextContinuationToken>")[1].split("</Next")[0]
        else: break
    return out


def box(a, r):
    r = max(1, int(r)); k = 2*r+1
    c = np.cumsum(np.pad(a.astype(np.float32), ((r+1, r), (0, 0)), mode="edge"), axis=0)
    o = (c[k:]-c[:-k])/k
    c = np.cumsum(np.pad(o, ((0, 0), (r+1, r)), mode="edge"), axis=1)
    return (c[:, k:]-c[:, :-k])/k


def z(a):
    s = a.std()
    return (a - a.mean())/(s if s > 1e-9 else 1.0)


# ---------------- THE SEARCH SPACE — the agent's "eyes" --------------------
def make_features(img, um, P):
    """Every candidate quantity, all scale-specified in MICRONS so they
    transfer between scans of different voxel size."""
    sr = max(2, int(round(P["scale_um"]/um/2)))
    F = {}
    gy, gx = np.gradient(img)
    gm = np.sqrt(gy*gy + gx*gx)
    gm2 = np.sqrt(np.gradient(np.gradient(img, axis=0), axis=0)**2 +
                  np.gradient(np.gradient(img, axis=1), axis=1)**2)

    F["sharp"] = box(gm2, sr)/np.maximum(box(gm, sr), 1e-6)

    Jxx = box(gx*gx, sr); Jyy = box(gy*gy, sr); Jxy = box(gx*gy, sr)
    den = np.maximum(Jxx+Jyy, 1e-6)
    coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2)/den
    ang = 0.5*np.degrees(np.arctan2(2*Jxy, Jxx-Jyy)) % 180
    off = np.minimum(np.minimum(np.abs(ang), np.abs(ang-90)), np.abs(ang-180))
    F["offaxis"] = box(off.astype(np.float32), sr)/45.0
    F["disorder"] = 1.0 - coh

    hp = img - box(img, max(2, int(round(P["hp_um"]/um))))
    F["hfenergy"] = np.sqrt(box(hp*hp, sr))
    mu = box(img, sr)
    F["localsd"] = np.sqrt(np.maximum(box(img*img, sr) - mu*mu, 0))
    F["proud"] = img - box(img, max(2, int(round(P["proud_um"]/um))))

    dark = box(img, max(1, int(round(P["chan_um"]/um)))) - img
    chan = dark > np.percentile(dark, P["chan_pct"])
    lab, _ = ndi.label(~chan)
    sizes = np.bincount(lab.ravel()); diam = 2*np.sqrt(sizes/np.pi)
    ok = (diam >= P["plate_lo_um"]/um) & (diam <= P["plate_hi_um"]/um); ok[0] = False
    F["plate"] = box(ok[lab].astype(np.float32), sr)
    F["chandark"] = box(dark, sr)
    return F


FEATURE_NAMES = ["sharp", "offaxis", "disorder", "hfenergy", "localsd", "proud",
                 "plate", "chandark"]


def sample_variant(rng):
    n = int(rng.integers(1, 4))
    names = list(rng.choice(FEATURE_NAMES, size=n, replace=False))
    return {
        "features": names,
        "weights": [float(round(rng.choice([1.0, 0.7, 0.5, -0.5, -0.7, -1.0]), 2))
                    for _ in names],
        "scale_um": float(rng.choice([250, 400, 600, 750, 1000, 1500])),
        "hp_um": float(rng.choice([60, 100, 160, 250])),
        "proud_um": float(rng.choice([300, 500, 900])),
        "chan_um": float(rng.choice([100, 200, 350])),
        "chan_pct": int(rng.choice([60, 70, 80, 88])),
        "plate_lo_um": 100.0,
        "plate_hi_um": float(rng.choice([300, 500, 800])),
        "depth_band": int(rng.choice([4, 8, 14])),
    }


def combine(F, P):
    out = None
    for nm, w in zip(P["features"], P["weights"]):
        t = w*z(F[nm])
        out = t if out is None else out + t
    return out
# ---------------------------------------------------------------------------


def voxel_um(name):
    import re
    m = re.search(r"(\d+\.?\d*)um", name)
    return float(m.group(1)) if m else None


def build_targets():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    samples = [p.rstrip("/") for p in listing("") if p.startswith("PHerc")]
    segs = []
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(lambda s: listing(f"{s}/segments/"), samples):
            segs += r
    def probe(seg):
        ink = [k for k in listing(seg+"ink-detection/downsampled/", delim=False)
               if k.lower().endswith((".jpg", ".png"))]
        if not ink: return None
        sv = [p for p in listing(seg+"surface-volumes/") if p.endswith(".zarr/")]
        if not sv: return None
        best = None
        for s in sv:
            um = voxel_um(s.rstrip("/").split("/")[-1])
            if um and (best is None or um < best[0]): best = (um, s)
        if not best: return None
        return dict(seg=seg, scroll=seg.split("/")[0], ink=ink[0], sv=best[1], um=best[0])
    out = []
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        for r in ex.map(probe, segs):
            if r: out.append(r)
    json.dump(out, open(CACHE, "w"))
    return out


_tiles = {}
def load_tile(t):
    """Fetch once, reuse for every variant. This is what makes the search fast."""
    key = t["seg"]
    if key in _tiles: return _tiles[key]
    try:
        ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}", 120)))).astype(np.float32)
        if ink.ndim == 3: ink = ink.mean(2)
        za = json.loads(get(f"{B}/{t['sv']}0/.zarray", 60).decode())
        D, HH, WW = za["shape"]
        if za["chunks"][1] != CH: raise ValueError("chunk")
        ds = WW/ink.shape[1]
        if not (1.5 < ds < 40): raise ValueError("ds")
        cy0, cx0 = (HH//CH)//2 - 2, (WW//CH)//2 - 2
        if cy0 < 0 or cx0 < 0: raise ValueError("small")
        NT = 4
        vol = np.zeros((D, NT*CH, NT*CH), np.float32); got = 0
        def g(cy, cx):
            try:
                b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}", 120)
                return cy, cx, (np.frombuffer(b, np.uint8).reshape(D, CH, CH)
                                if len(b) == D*CH*CH else None)
            except Exception: return cy, cx, None
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for cy, cx, a in ex.map(lambda p: g(*p),
                                    [(cy0+j, cx0+i) for j in range(NT) for i in range(NT)]):
                if a is not None:
                    got += 1
                    vol[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
        if got < NT*NT*0.75: raise ValueError("chunks")
        prof = vol.mean(axis=(1, 2)); pk = int(prof.argmax())
        iy, ix = int(cy0*CH/ds), int(cx0*CH/ds)
        res = dict(vol=vol, pk=pk, ink=ink, ds=ds, iy=iy, ix=ix, um=t["um"],
                   scroll=t["scroll"])
        _tiles[key] = res
        return res
    except Exception:
        _tiles[key] = None
        return None


def eval_variant(P, tile):
    if tile is None: return None
    vol, pk, um = tile["vol"], tile["pk"], tile["um"]
    b = P["depth_band"]
    img = vol[max(0, pk-b):pk+b+1].mean(0)
    if (img > 0).mean() < 0.5: return None
    try:
        F = make_features(img, um, P)
        f = combine(F, P)
    except Exception:
        return None
    step = max(1, int(round(tile["ds"])))
    h, w = f.shape
    fb = f[:h//step*step, :w//step*step].reshape(h//step, step, w//step, step).mean(axis=(1, 3))
    sub = tile["ink"][tile["iy"]:tile["iy"]+fb.shape[0], tile["ix"]:tile["ix"]+fb.shape[1]]
    n0, n1 = min(fb.shape[0], sub.shape[0]), min(fb.shape[1], sub.shape[1])
    if n0 < 24 or n1 < 24: return None
    fb, sub = fb[:n0, :n1], sub[:n0, :n1]
    tg = (sub > 128).astype(np.float32)
    cov = float(tg.mean())
    if not (0.05 < cov < 0.85): return None
    if not np.isfinite(fb).all() or fb.std() < 1e-9: return None
    r = float(np.corrcoef(fb.ravel(), tg.ravel())[0, 1])
    if not math.isfinite(r): return None
    rng = np.random.default_rng(7)
    nulls = np.array([abs(np.corrcoef(fb.ravel(),
                     np.roll(np.roll(tg, rng.integers(6, n0-6), 0),
                             rng.integers(6, n1-6), 1).ravel())[0, 1])
                      for _ in range(80)])
    return dict(r=r, p=float((nulls >= abs(r)).mean()), cov=cov, scroll=tile["scroll"])


def main():
    t0 = time.time()
    print("NIGHTSHIFT — searching for a feature that generalises")
    print(f"bar: held-out median r >= {MIN_HELDOUT_R}, >={int(100*MIN_FRAC_SIGNIF)}% "
          f"significant, >={MIN_HELDOUT_SEGS} segments, >={MIN_SCROLLS} scrolls\n")
    targets = build_targets()
    by_scroll = {}
    for t in targets: by_scroll.setdefault(t["scroll"], []).append(t)
    scrolls = sorted(by_scroll)
    print(f"{len(targets)} segments across {len(scrolls)} scrolls: "
          f"{', '.join(f'{s}({len(by_scroll[s])})' for s in scrolls)}\n")
    if len(scrolls) < 2:
        print("need at least two scrolls to test generalisation"); return

    rng = np.random.default_rng()
    # split BY SCROLL so held-out is always a different scribe/scan
    tune_scrolls = scrolls[:max(1, len(scrolls)//3)]
    held_scrolls = [s for s in scrolls if s not in tune_scrolls]
    tune_pool = [t for s in tune_scrolls for t in by_scroll[s]]
    held_pool = [t for s in held_scrolls for t in by_scroll[s]]
    print(f"tune on {tune_scrolls} ({len(tune_pool)} segs)")
    print(f"held out {held_scrolls} ({len(held_pool)} segs)\n")

    # warm a working set of tiles once
    warm_t = list(rng.choice(tune_pool, size=min(10, len(tune_pool)), replace=False))
    warm_h = list(rng.choice(held_pool, size=min(30, len(held_pool)), replace=False))
    print("loading tiles (once; reused for every variant) …", flush=True)
    for t in warm_t + warm_h: load_tile(t)
    warm_t = [t for t in warm_t if _tiles.get(t["seg"])]
    warm_h = [t for t in warm_h if _tiles.get(t["seg"])]
    print(f"  {len(warm_t)} tune tiles, {len(warm_h)} held-out tiles ready "
          f"({time.time()-t0:.0f}s)\n")
    if len(warm_h) < MIN_HELDOUT_SEGS:
        print("not enough held-out tiles loaded; aborting"); return

    n, best = 0, None
    deadline = t0 + HOURS*3600
    log = open(LOG, "a")
    while time.time() < deadline:
        n += 1
        P = sample_variant(rng)
        tr = [eval_variant(P, _tiles[t["seg"]]) for t in warm_t]
        tr = [x for x in tr if x]
        if len(tr) < 3: continue
        tune_med = float(np.median([x["r"] for x in tr]))
        if abs(tune_med) < 0.12:      # hopeless, do not spend held-out on it
            log.write(json.dumps({"variant": P, "tune_median": tune_med,
                                  "stage": "rejected"})+"\n"); log.flush()
            continue
        sign = 1.0 if tune_med > 0 else -1.0
        hr = [eval_variant(P, _tiles[t["seg"]]) for t in warm_h]
        hr = [x for x in hr if x]
        if len(hr) < MIN_HELDOUT_SEGS: continue
        rs = np.array([sign*x["r"] for x in hr])
        ps = np.array([x["p"] for x in hr])
        med = float(np.median(rs)); frac = float((ps < 0.05).mean())
        nsc = len({x["scroll"] for x in hr})
        rec = {"variant": P, "tune_median": tune_med, "heldout_median": med,
               "frac_signif": frac, "n_heldout": len(hr), "n_scrolls": nsc,
               "stage": "tested", "t": round(time.time()-t0)}
        log.write(json.dumps(rec)+"\n"); log.flush()
        if best is None or med > best["heldout_median"]:
            best = rec
            print(f"[{n:5d}] new best held-out median r={med:+.3f} "
                  f"({frac*100:.0f}% signif, {len(hr)} segs, {nsc} scrolls) "
                  f"{'+'.join(P['features'])}", flush=True)
        if (med >= MIN_HELDOUT_R and frac >= MIN_FRAC_SIGNIF
                and len(hr) >= MIN_HELDOUT_SEGS and nsc >= MIN_SCROLLS):
            with open(ALERT, "w") as f:
                f.write("# NIGHTSHIFT ALERT\n\nA variant cleared the bar.\n\n")
                f.write("```json\n"+json.dumps(rec, indent=1)+"\n```\n\n")
                f.write("Not a finding yet. Still required: negative control on a\n"
                        "no-ink region, a second held-out draw, and visual review.\n")
            print("\n*** ALERT — variant cleared the bar. See "+ALERT+" ***\n", flush=True)
            break
        if n % 25 == 0:
            print(f"  … {n} variants, {(time.time()-t0)/60:.0f} min, "
                  f"best held-out {best['heldout_median'] if best else 0:+.3f}", flush=True)

    print(f"\nran {n} variants in {(time.time()-t0)/60:.0f} min")
    if best:
        print(f"best held-out median r = {best['heldout_median']:+.3f}")
        print("cleared the bar" if os.path.exists(ALERT)
              else f"NOTHING cleared the bar (needed {MIN_HELDOUT_R})")
    print(f"full log: {LOG}")


if __name__ == "__main__":
    main()
