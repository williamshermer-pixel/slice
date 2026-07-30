"""PACK — shared infrastructure for every search team.

Exists because four teams each re-downloading the same 30 tiles from S3 is the
single largest waste in the pipeline. A tile is a whole depth stack of a
4x4-chunk window; fetching one costs ~30s of network. Fetch it once, put it on
disk, and every team afterwards starts in seconds.

Also holds the three things every team must use identically, so results are
comparable across teams:

  height_map()    the sheet as a height field, band-passed at stroke scale
  score_vs_ink()  correlation against published ink, with a SPATIAL null
  neg_control()   the same measure on blank papyrus

That last one is the lesson of the first overnight run. Every high scorer the
swarm produced fired just as hard on papyrus with no ink on it — they had
learned "this sheet is well preserved", which correlates with "there is text
here" without being about ink at all. So the negative control is not an
afterthought here, it is part of the score:

    final = heldout_median - PENALTY * negative_control_r

A papyrus detector now scores near zero by construction and cannot win.

Nothing in here is allowed to confirm anything. It measures, and it subtracts.
"""
import os, io, sys, json, math, hashlib, urllib.request, concurrent.futures as cf
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH = 128
# NOT /private/tmp. macOS purges it, and it did — a reboot took out 5 GB of
# cached tiles, the target list, and twelve running workers at once. Home
# directory survives reboots; the repo does not hold scroll data, which is
# CC BY-NC and must never be committed.
CACHE_DIR = os.environ.get("INK_CACHE",
                           os.path.expanduser("~/.ink-cache"))
TARGETS = os.path.join(CACHE_DIR, "targets.json")
# The target list is derived METADATA — S3 paths and voxel sizes, no pixels —
# so a copy lives in the repo and is version-controlled. Rebuilding it from S3
# takes minutes of listing calls; losing it should never block a relaunch.
SEED_TARGETS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "findings", "targets.json")
os.makedirs(CACHE_DIR, exist_ok=True)

# how hard a candidate is punished for firing on blank papyrus.
# 1.5 means a detector needs r=+0.30 on ink while staying under 0.10 on blank
# just to beat a detector scoring +0.15 that is silent on blank.
NEG_PENALTY = 1.5

# Layers kept each side of the sheet peak, IN MEMORY.
#
# A surface chunk is the whole depth stack of a tile in one object, so a fetched
# tile can be 250 layers — 260 MB as float32. Fourteen dogs holding 36 tiles
# each would need terabytes. Nothing in this project looks further than ~20
# layers from the sheet peak (PCA uses 20, RTI uses 10, the texture bank 14), so
# everything past that is paid for and never read.
#
# Cropped to +/-28 and held as uint8 a tile is 15 MB, and a whole dog's working
# set is under 600 MB. The disk cache still holds the full stack, so widening
# this later costs nothing but a re-read.
KEEP = 28


def get(u, t=120):
    return urllib.request.urlopen(u, timeout=t).read()


# ---------------------------------------------------------------------------
# targets
# ---------------------------------------------------------------------------
def targets():
    """The 255 segments across 7 scrolls that have published ink detections.

    Three sources in order: the working cache, the version-controlled seed in
    the repo, then a rebuild from S3. A reboot that clears the cache should
    cost seconds, not a re-listing of the whole bucket.
    """
    if os.path.exists(TARGETS):
        return json.load(open(TARGETS))
    if os.path.exists(SEED_TARGETS):
        tg = json.load(open(SEED_TARGETS))
        json.dump(tg, open(TARGETS, "w"))
        return tg
    tg = rebuild_targets()
    json.dump(tg, open(TARGETS, "w"))
    try:
        json.dump(tg, open(SEED_TARGETS, "w"))
    except Exception:
        pass
    return tg


def rebuild_targets():
    """Re-derive the target list from the bucket. Slow; the seed exists so this
    is a last resort rather than a routine step."""
    _argv, sys.argv = sys.argv, [sys.argv[0]]
    try:
        import nightshift as NS
        return NS.build_targets()
    finally:
        sys.argv = _argv


SCALES = os.path.join(CACHE_DIR, "voxel_scales.json")


def true_um(t):
    """Voxel size from the volume's OME metadata — NOT from its filename.

    This project spent its whole life parsing the micron figure out of the
    surface-volume filename, e.g. "1.129um-0.22m-59keV-...zarr". That number is
    the ORIGINAL SCAN resolution. The array we actually read is level 0 of that
    volume's pyramid, and its coordinateTransformations scale is 2.258 um —
    exactly 2x coarser — on four of the seven scrolls.

    Consequence of the bug: every scale specified in microns (the 350 um
    stroke, the 200-600 um fibre band, every band-pass and box radius) was
    converted to a pixel radius twice as large as intended on those scrolls. So
    features aimed at the letter stroke were measuring something at double the
    size, which is a plausible contributor to fourteen negatives.

    Cached, because it costs one metadata GET per volume.
    """
    try:
        cache = json.load(open(SCALES))
    except Exception:
        cache = {}
    sv = t["sv"]
    if sv in cache:
        return cache[sv]
    try:
        z = json.loads(get(f"{B}/{sv}.zattrs", 45).decode())
        ms = z["multiscales"][0]
        d0 = ms["datasets"][0]
        sc = [c for c in d0["coordinateTransformations"] if c["type"] == "scale"][0]
        v = float(sc["scale"][0])
    except Exception as e:
        # FAIL LOUDLY, and do NOT persist the failure. Caching None here made
        # `if sv in cache: return cache[sv]` return None forever, and every
        # caller then falls back to t["um"] — the filename value — silently
        # reinstating the 2x scale bug that this function exists to prevent.
        # One network blip must not permanently corrupt the scale of the run.
        print(f"WARNING: could not read voxel scale for {sv}: {e}", flush=True)
        return None
    cache[sv] = v
    try:
        json.dump(cache, open(SCALES, "w"))
    except Exception:
        pass
    return v


INK_LAYER_UM = 15.0     # the ink layer thickness that governs this project
MIN_VOXELS = 3.0        # fewer than ~3 samples cannot resolve a feature at all


def voxels_through_ink(um):
    return INK_LAYER_UM/float(um)


def strata(tg, n_tune=2):
    """Split scrolls by whether the scan can resolve the ink layer AT ALL.

    This is not a refinement, it is a correction. The original split sorted
    scroll names alphabetically and took the first third to tune on, which put
    PHerc0172 in the tuning set. PHerc0172's finest surface volume is 7.91
    um/voxel — 1.9 voxels through a 15 um ink layer, below the ~3 needed to
    resolve a feature. The ink there was never sampled. Half of every tuning
    signal was therefore coming from a scroll that physically cannot show ink.

    The blind scroll is not discarded. It becomes a PHYSICS CONTROL, and a
    strong one: a measure that fires just as hard where the ink was never
    sampled is not measuring ink, whatever it scores elsewhere. Unlike the
    blank-papyrus control, which argues from an absence of ink, this argues
    from an absence of RESOLUTION on sheets that do carry text — so it catches
    confounds the blank control cannot.

    Returns (by_scroll, um_per_scroll, tune_scrolls, held_scrolls, blind_scrolls).
    """
    by = {}
    for t in tg:
        by.setdefault(t["scroll"], []).append(t)
    um = {s: float(np.median([x["um"] for x in v])) for s, v in by.items()}
    resolvable = sorted([s for s in by if voxels_through_ink(um[s]) >= MIN_VOXELS],
                        key=lambda s: (um[s], s))
    blind = sorted([s for s in by if voxels_through_ink(um[s]) < MIN_VOXELS])
    return by, um, resolvable[:n_tune], resolvable[n_tune:], blind


def split_by_scroll(tg, tune_frac=3):
    """Split BY SCROLL, never by tile. Held-out must be a different scribe and
    a different scan, or 'held out' means nothing."""
    by = {}
    for t in tg:
        by.setdefault(t["scroll"], []).append(t)
    scrolls = sorted(by)
    tune_s = scrolls[:max(1, len(scrolls)//tune_frac)]
    held_s = [s for s in scrolls if s not in tune_s]
    return (by,
            [t for s in tune_s for t in by[s]],
            [t for s in held_s for t in by[s]],
            tune_s, held_s)


# ---------------------------------------------------------------------------
# tiles, cached to disk
# ---------------------------------------------------------------------------
_mem = {}


def _cache_path(seg):
    return os.path.join(CACHE_DIR, hashlib.md5(seg.encode()).hexdigest() + ".npz")


def _crop(res):
    """Keep only the depth window around the sheet peak, as uint8.

    This is what makes a pack of dogs fit in memory at all. See KEEP above.
    """
    if res is None:
        return None
    v, pk = res["vol"], res["pk"]
    a, b = max(0, pk-KEEP), min(v.shape[0], pk+KEEP+1)
    res["vol8"] = np.ascontiguousarray(v[a:b]).astype(np.uint8)
    res["pk"] = pk - a
    res.pop("vol", None)
    return res


def layers(tile, lo, hi):
    """float32 copy of layers [lo, hi) — converted on demand, never stored."""
    v = tile["vol8"]
    return v[max(0, lo):min(v.shape[0], hi)].astype(np.float32)


def load_tile(t, nt=4):
    """Depth window around the sheet, plus the ink ground truth.

    Cached to disk as uint8 — the volume is uint8 on S3 and float conversion is
    cheap, so storing float32 would quadruple the cache for nothing. The disk
    copy keeps the FULL stack; only the in-memory copy is cropped.
    """
    seg = t["seg"]
    if seg in _mem:
        return _mem[seg]
    p = _cache_path(seg)
    if os.path.exists(p):
        try:
            d = np.load(p, allow_pickle=False)
            if d["vol"].size == 0:
                _mem[seg] = None
                return None
            um_true = true_um(t) or float(d["um"])
            res = _crop(dict(vol=d["vol"], pk=int(d["pk"]),
                             ink=d["ink"].astype(np.float32), ds=float(d["ds"]),
                             iy=int(d["iy"]), ix=int(d["ix"]), um=um_true,
                             scroll=str(t["scroll"]), seg=seg))
            _mem[seg] = res
            return res
        except Exception:
            pass
    res = _fetch_tile(t, nt)
    try:
        if res is None:
            np.savez_compressed(p, vol=np.zeros((0,), np.uint8))
        else:
            np.savez(p, vol=res["vol"].astype(np.uint8), pk=res["pk"],
                     ink=res["ink"].astype(np.uint8), ds=res["ds"],
                     iy=res["iy"], ix=res["ix"], um=res["um"])
    except Exception:
        pass
    res = _crop(res)
    _mem[seg] = res
    return res


def _fetch_tile(t, nt):
    try:
        ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
        if ink.ndim == 3:
            ink = ink.mean(2)
        za = json.loads(get(f"{B}/{t['sv']}0/.zarray", 60).decode())
        D, HH, WW = za["shape"]
        if za["chunks"][1] != CH:
            return None
        ds = WW/ink.shape[1]
        if not (1.5 < ds < 40):
            return None
        cy0, cx0 = (HH//CH)//2 - nt//2, (WW//CH)//2 - nt//2
        if cy0 < 0 or cx0 < 0:
            return None
        vol = np.zeros((D, nt*CH, nt*CH), np.float32)
        got = 0

        def g(cy, cx):
            try:
                b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
                return cy, cx, (np.frombuffer(b, np.uint8).reshape(D, CH, CH)
                                if len(b) == D*CH*CH else None)
            except Exception:
                return cy, cx, None

        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for cy, cx, a in ex.map(lambda q: g(*q),
                                    [(cy0+j, cx0+i) for j in range(nt) for i in range(nt)]):
                if a is not None:
                    got += 1
                    vol[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
        if got < nt*nt*0.75:
            return None
        prof = vol.mean(axis=(1, 2))
        return dict(vol=vol, pk=int(prof.argmax()), ink=ink, ds=ds,
                    iy=int(cy0*CH/ds), ix=int(cx0*CH/ds),
                    um=float(true_um(t) or t["um"]),
                    scroll=t["scroll"], seg=t["seg"])
    except Exception:
        return None


def warm(tiles, workers=6, verbose=True):
    """Fill the disk cache in parallel. Network-bound, so threads are fine."""
    todo = [t for t in tiles if not os.path.exists(_cache_path(t["seg"]))]
    if verbose and todo:
        print(f"  warming {len(todo)} uncached tiles ({len(tiles)-len(todo)} already on disk)",
              flush=True)
    if todo:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(load_tile, todo))
    out = [t for t in tiles if load_tile(t) is not None]
    if verbose:
        print(f"  {len(out)}/{len(tiles)} tiles ready", flush=True)
    return out


# ---------------------------------------------------------------------------
# image primitives
# ---------------------------------------------------------------------------
def box(a, r):
    """Separable box blur by cumulative sum. O(n) regardless of radius, which
    matters because the scales here run to 1500 um = hundreds of voxels."""
    r = max(1, int(r))
    k = 2*r+1
    c = np.cumsum(np.pad(a.astype(np.float32), ((r+1, r), (0, 0)), mode="edge"), axis=0)
    o = (c[k:]-c[:-k])/k
    c = np.cumsum(np.pad(o, ((0, 0), (r+1, r)), mode="edge"), axis=1)
    return (c[:, k:]-c[:, :-k])/k


def z(a):
    s = a.std()
    return (a - a.mean())/(s if s > 1e-9 else 1.0)


def bandpass(a, um, lo_um, hi_um):
    """Keep structure between two physical scales. Everything in this project
    is specified in microns rather than pixels so it transfers between scans of
    different voxel size — 1.129 um/vox on PHerc 0139 against 8.64 on the
    unread scrolls."""
    lo = max(1, int(round(lo_um/um/2)))
    hi = max(lo+1, int(round(hi_um/um/2)))
    return box(a, lo) - box(a, hi)


# ---------------------------------------------------------------------------
# the sheet as a height field
# ---------------------------------------------------------------------------
def height_map(tile, band=10, um_per_layer=None):
    """Sub-voxel surface height from the depth stack.

    Intensity-weighted centroid of depth around the peak layer. This is better
    than argmax by roughly the interpolation factor: argmax quantises to whole
    layers, which at 1.13 um/voxel throws away exactly the scale the ink lives
    at (~15 um layer, 0.35 mm stroke).

    Returns height in MICRONS, mean-subtracted.
    """
    pk, um = tile["pk"], tile["um"]
    if um_per_layer is None:
        um_per_layer = um
    nz = tile["vol8"].shape[0]
    a, b = max(0, pk-band), min(nz, pk+band+1)
    w = layers(tile, a, b)
    d = np.arange(a-pk, b-pk, dtype=np.float32)[:, None, None]
    s = w.sum(0)
    s = np.maximum(s, 1e-6)
    h = (w*d).sum(0)/s
    h = h*um_per_layer
    return h - h.mean(), (b-a)


def mid_image(tile, band, offset=0):
    """Mean of a depth band, centred `offset` layers from the sheet peak.

    The offset is the axis nobody swept. Every measure in this project averaged
    a band centred on the peak, which smears a depth-localised signal into its
    neighbours — and ink is a SURFACE layer, so if it is anywhere it is at a
    particular depth, not spread through the sheet. A rapid depth probe showed
    transforms whose response varies by 4x across +/-18 layers, which a
    peak-centred band cannot express at all.
    """
    # Clamp so the band stays inside the volume. An unclamped offset walks the
    # window off the end and layers() returns an empty slice, whose mean is NaN
    # — which then silently poisons every downstream feature rather than
    # failing loudly.
    nz = tile["vol8"].shape[0]
    pk = int(np.clip(tile["pk"] + int(offset), band, max(band, nz-band-1)))
    return layers(tile, pk-band, pk+band+1).mean(0)


# ---------------------------------------------------------------------------
# scoring — the only place a number is allowed to be produced
# ---------------------------------------------------------------------------
def _align(f, tile):
    """Bin the feature map down to the ink map's grid and crop to overlap."""
    step = max(1, int(round(tile["ds"])))
    h, w = f.shape
    fb = f[:h//step*step, :w//step*step].reshape(h//step, step, w//step, step).mean(axis=(1, 3))
    sub = tile["ink"][tile["iy"]:tile["iy"]+fb.shape[0], tile["ix"]:tile["ix"]+fb.shape[1]]
    n0, n1 = min(fb.shape[0], sub.shape[0]), min(fb.shape[1], sub.shape[1])
    if n0 < 24 or n1 < 24:
        return None, None
    return fb[:n0, :n1], sub[:n0, :n1]


def score_vs_ink(f, tile, nulls=80, require_cov=(0.02, 0.90)):
    # The gate exists to stop degenerate correlations on tiles that are almost
    # entirely blank or entirely ink. It was 0.05, but median coverage across
    # the published set is 0.051 — so the gate was throwing away HALF the
    # corpus, leaving every variant scored on 8-9 tiles against a floor of 8.
    # Variants that fell one tile short were dropped unevaluated. At 0.02 the
    # same pool yields 33 of 40 tiles instead of 24.
    """Correlation against published ink, with a SPATIAL null.

    The null shifts the target and preserves its autocorrelation. A
    pixel-permutation null is invalid on data this spatially correlated and will
    hand back p=0.0000 on pure noise — that mistake cost a night earlier in this
    project.
    """
    fb, sub = _align(f, tile)
    if fb is None:
        return None
    tg = (sub > 128).astype(np.float32)
    cov = float(tg.mean())
    if require_cov and not (require_cov[0] < cov < require_cov[1]):
        return None
    if not np.isfinite(fb).all() or fb.std() < 1e-9 or tg.std() < 1e-9:
        return None
    r = float(np.corrcoef(fb.ravel(), tg.ravel())[0, 1])
    if not math.isfinite(r):
        return None
    n0, n1 = tg.shape
    rng = np.random.default_rng(7)
    nl = np.array([abs(np.corrcoef(fb.ravel(),
                   np.roll(np.roll(tg, int(rng.integers(6, n0-6)), 0),
                           int(rng.integers(6, n1-6)), 1).ravel())[0, 1])
                   for _ in range(nulls)])
    return dict(r=r, p=float((nl >= abs(r)).mean()), cov=cov,
                scroll=tile["scroll"], seg=tile["seg"])


COVER = os.path.join(CACHE_DIR, "ink_coverage.json")


def ink_coverage(t):
    """What fraction of a segment's published ink map is ink.

    Reads ONLY the ink JPEG — a few hundred KB — never the volume. The first
    version of this loaded whole tiles to check coverage, which meant scanning
    for blank papyrus cost more than the search it was supposed to control, so
    it gave up after a handful and the control ran on two tiles. Cached, so the
    scan is paid once for the whole project.
    """
    try:
        cov = json.load(open(COVER))
    except Exception:
        cov = {}
    seg = t["seg"]
    if seg in cov:
        return cov[seg]
    try:
        ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
        if ink.ndim == 3:
            ink = ink.mean(2)
        v = float((ink > 128).mean())
    except Exception:
        v = None
    cov[seg] = v
    try:
        json.dump(cov, open(COVER, "w"))
    except Exception:
        pass
    return v


def scan_coverage(pool, workers=12):
    """Fill the coverage cache for a pool, in parallel. Network-bound."""
    todo = [t for t in pool]
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        vals = list(ex.map(ink_coverage, todo))
    out = {}
    for t, v in zip(todo, vals):
        if v is not None:
            out[t["seg"]] = v
    try:
        prev = json.load(open(COVER))
    except Exception:
        prev = {}
    prev.update(out)
    json.dump(prev, open(COVER, "w"))
    return out


def condition_covariates(tile, scale_um=600.0):
    """Per-pixel maps of the things that are NOT ink but track it.

    Sheet brightness, local contrast, fibre coherence and large-scale curvature.
    All computed from the volume, no labels, so nothing here can leak.
    """
    um = tile["um"]
    img = mid_image(tile, 8)
    r = max(2, int(round(scale_um/um/2)))
    mu = box(img, r)
    sd = np.sqrt(np.maximum(box(img*img, r) - mu*mu, 0))
    gy, gx = np.gradient(img)
    Jxx, Jyy, Jxy = box(gx*gx, r), box(gy*gy, r), box(gx*gy, r)
    coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2)/np.maximum(Jxx+Jyy, 1e-6)
    h, _ = height_map(tile, band=10)
    curv = box(h, max(2, int(round(3000.0/um/2))))
    return [mu, sd, coh, curv]


def _residualise(y, X):
    """Least-squares residual of y on columns of X (plus intercept)."""
    A = np.column_stack([np.ones(len(y))] + [c for c in X])
    try:
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    except Exception:
        return None
    return y - A @ beta


def score_partial(f, tile, nulls=80, require_cov=(0.02, 0.90)):
    """Correlation of feature with ink AFTER removing measured sheet condition
    from BOTH sides.

    This is the principled version of the fix. Penalising a candidate for
    firing on blank papyrus taxes the confound; partial correlation removes it,
    and asks the question that actually matters:

        does this feature explain ink BEYOND what sheet condition explains?

    It also makes the objective reachable. Blank-papyrus |r| sits at 0.09-0.25
    for essentially every measure tried in this project, so a penalty of
    1.5*blank demands a raw correlation higher than anything ever recorded
    here — a bar nothing can clear, which produces guaranteed silence and
    teaches nothing.

    Reported alongside the raw number, never instead of it.
    """
    fb, sub = _align(f, tile)
    if fb is None:
        return None
    tg = (sub > 128).astype(np.float32)
    cov = float(tg.mean())
    if require_cov and not (require_cov[0] < cov < require_cov[1]):
        return None
    if not np.isfinite(fb).all() or fb.std() < 1e-9 or tg.std() < 1e-9:
        return None

    C = []
    for c in condition_covariates(tile):
        cb, _ = _align(c, tile)
        if cb is None or cb.shape != fb.shape:
            return None
        C.append(cb.ravel().astype(np.float64))
    rf = _residualise(fb.ravel().astype(np.float64), C)
    rt = _residualise(tg.ravel().astype(np.float64), C)
    if rf is None or rt is None or rf.std() < 1e-9 or rt.std() < 1e-9:
        return None
    r = float(np.corrcoef(rf, rt)[0, 1])
    if not math.isfinite(r):
        return None

    n0, n1 = tg.shape
    rng = np.random.default_rng(7)
    nl = []
    for _ in range(nulls):
        sh = np.roll(np.roll(tg, int(rng.integers(6, n0-6)), 0),
                     int(rng.integers(6, n1-6)), 1)
        rs = _residualise(sh.ravel().astype(np.float64), C)
        if rs is None or rs.std() < 1e-9:
            continue
        nl.append(abs(np.corrcoef(rf, rs)[0, 1]))
    p = float((np.array(nl) >= abs(r)).mean()) if nl else 1.0
    return dict(r=r, p=p, cov=cov, scroll=tile["scroll"], seg=tile["seg"])


def crop_coverage(t):
    """Ink fraction of the region a score is ACTUALLY computed on.

    Not the same as whole-map coverage, and the difference invalidated a whole
    night's conclusions. A segment can be 99.5% blank overall while the central
    4x4-chunk window that every measurement uses sits directly on a column of
    text. Controls must be chosen on this number, never on the map-wide one.
    """
    tile = load_tile(t)
    if tile is None:
        return None
    fb, sub = _align(mid_image(tile, 8), tile)
    if fb is None:
        return None
    return float((sub > 128).mean())


def find_negatives(pool, n=8, max_cov=0.02, crop_max=0.005, scan=28):
    """Segments whose TESTED REGION is blank papyrus. The control set.

    Two-stage: rank cheaply by whole-map coverage (ink JPEG only), then verify
    the aligned crop is genuinely empty before accepting a tile as a control.

    The first version of this ranked by whole-map coverage alone. Six controls
    chosen that way included two whose tested crops were 2.2% and 8.6% ink, so
    the "negative control" was partly scoring real ink detection and marking it
    a failure. The original forensics pass was worse: it selected controls the
    same way and then scored them through a function that REQUIRES 5-85% crop
    coverage, so its controls only ever ran on crops full of ink. Every
    "fires on blank papyrus" verdict it produced is therefore unsafe.
    """
    cov = scan_coverage(pool)
    by = {t["seg"]: t for t in pool}
    ranked = [s for s, v in sorted(cov.items(), key=lambda kv: kv[1])
              if s in by and v < max_cov] or \
             [s for s, _ in sorted(cov.items(), key=lambda kv: kv[1]) if s in by]

    # Spread across scrolls, emptiest first within each. A control set drawn
    # purely by coverage lands almost entirely on one scroll — the one with the
    # most segments — and then it only proves a detector is quiet on THAT
    # scroll's blank papyrus. Round-robin makes the control test the thing it
    # claims to test.
    per = {}
    for s in ranked:
        per.setdefault(by[s]["scroll"], []).append(s)
    order, i = [], 0
    while len(order) < scan and any(len(v) > i for v in per.values()):
        for sc in sorted(per):
            if len(per[sc]) > i and len(order) < scan:
                order.append(per[sc][i])
        i += 1

    # verify on the crop that is actually scored
    keep = []
    for s in order:
        c = crop_coverage(by[s])
        if c is not None and c <= crop_max:
            keep.append(s)
        if len(keep) >= n:
            break
    return [by[s] for s in keep]


def neg_control(fn, negs):
    """Median |r| where there is no ink. A real detector goes quiet here.

    Note the target on a blank tile is nearly all zeros, so coverage gating is
    switched off — that is the whole point of the control.
    """
    rs = []
    for t in negs:
        tile = load_tile(t)
        if tile is None:
            continue
        try:
            f = fn(tile)
        except Exception:
            continue
        if f is None:
            continue
        fb, sub = _align(f, tile)
        if fb is None or fb.std() < 1e-9:
            continue
        tg = sub.astype(np.float32)
        if tg.std() < 1e-9:
            continue
        r = float(np.corrcoef(fb.ravel(), tg.ravel())[0, 1])
        if math.isfinite(r):
            rs.append(abs(r))
    return float(np.median(rs)) if rs else None


def penalised(heldout_median, negative_r, penalty=NEG_PENALTY):
    """THE FIX. The first overnight run scored candidates on held-out ink alone
    and every winner was a papyrus-condition detector. Subtracting the control
    inside the objective means that family can never climb again."""
    if negative_r is None:
        return heldout_median - penalty*0.25   # unmeasured control is not free
    return heldout_median - penalty*negative_r


# ---------------------------------------------------------------------------
# AUC scoring — added after correlation was shown to be the wrong instrument
# ---------------------------------------------------------------------------
def auc_vs_ink(f, tile, thr=128, nulls=60, require_cov=(0.02, 0.90)):
    """Rank-based detection score, with a SPATIAL null.

    Correlation against a sparse binary target is dominated by the ~95% of
    pixels that are blank, and the positive control showed it saturates: ink
    injected at 100% of sheet contrast still only reached r = 0.484. Fourteen
    mechanisms were judged with an instrument that cannot register.

    AUC asks the question a detector is actually for — if I rank every pixel by
    this feature, do ink pixels come out on top? — and is insensitive to the
    background mass. Reported folded to >= 0.5 so polarity does not matter.

    The null shifts the TARGET and preserves its autocorrelation, exactly as in
    score_vs_ink. A permutation null is invalid on data this spatially
    correlated and will report significance on noise.
    """
    fb, sub = _align(f, tile)
    if fb is None or fb.std() < 1e-9:
        return None
    tg = sub > thr
    cov = float(tg.mean())
    if require_cov and not (require_cov[0] < cov < require_cov[1]):
        return None
    x = fb.ravel()
    def _a(y):
        n1 = int(y.sum()); n0 = len(y) - n1
        if n1 < 50 or n0 < 50:
            return None
        o = np.argsort(x)
        rk = np.empty(len(x), float)
        rk[o] = np.arange(1, len(x)+1)
        a = (rk[y].sum() - n1*(n1+1)/2.0)/(n1*n0)
        return float(max(a, 1.0-a))
    a = _a(tg.ravel())
    if a is None:
        return None
    n0r, n1r = tg.shape
    rng = np.random.default_rng(7)
    nl = []
    for _ in range(nulls):
        sh = np.roll(np.roll(tg, int(rng.integers(6, n0r-6)), 0),
                     int(rng.integers(6, n1r-6)), 1)
        v = _a(sh.ravel())
        if v is not None:
            nl.append(v)
    p = float((np.array(nl) >= a).mean()) if nl else 1.0
    return dict(auc=a, p=p, cov=cov, scroll=tile["scroll"], seg=tile["seg"],
                null_median=float(np.median(nl)) if nl else None)
