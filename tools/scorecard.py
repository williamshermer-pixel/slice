"""SCORECARD — the validation harness, per candidate.

Implements the spec's §2.1, §2.3, §4.2 and §6 as one artifact. The governing
sentence is the spec's own:

    "Real ink is stubborn: the same letter keeps appearing. Artifacts flicker
     in and out."

So the central measure here is not a correlation, and not even an AUC. It is
AGREEMENT ACROSS INDEPENDENT SAMPLINGS of the same region — a Jaccard overlap
of the top-scoring pixels when the same detector is run at different depth
offsets and different parameters. A real stroke is in the same place every
time. An artifact moves.

Six checks, each able only to lower confidence:

  1 STABILITY (§2.3, §4.2)  Jaccard overlap of the top-k% mask across depth
                            offsets and parameter jitters. The trust standard.
  2 DEPTH COHERENCE (§2.1)  per-pixel argmax depth, then how much of it agrees
                            with its own neighbourhood. Ink sits on a surface,
                            so its depth map should vary GENTLY. Noise does not.
                            Uses no labels at all.
  3 DETECTION (§6)          AUC on held-out tiles, against its own spatial null
  4 PRECISION (§6)          precision at the top 5% of pixels — weighted toward
                            precision because a false letter costs more than a
                            missed one
  5 ARTIFACT CONTROLS (§6)  verified-blank papyrus and the blind scroll, where
                            the ink was never sampled at 1.9 voxels
  6 EVIDENCE                the raw, un-retouched map beside the published ink

Nothing in here can confirm a candidate. It reports a card; a human reads it.

Usage:
    python3 scorecard.py weave_fill
    python3 scorecard.py weave_amp 14
"""
import os, sys, json, time
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

_argv, sys.argv = sys.argv, [sys.argv[0]]
import weave as WV
import scent as SC
try:
    import nightshift as NS
    HAVE_NS = True
except Exception:
    HAVE_NS = False
sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "scorecard")
os.makedirs(OUT, exist_ok=True)

DEPTHS = [-9, -6, -3, 0, 3, 6, 9]
TOPK = 0.05          # fraction of pixels called "ink" when binarising


def build(name):
    """Return fn(tile, params) -> map, for any feature in the banks."""
    if name in WV.WEAVE_NAMES:
        return lambda tl, p: WV.weave_features(tl, p).get(name)
    if name in SC.SCENT_NAMES:
        return lambda tl, p: SC.scent_features(tl, p).get(name)
    if HAVE_NS:
        def f(tl, p):
            img = P.mid_image(tl, int(p.get("band", 8)), int(p.get("offset", 0)))
            if (img > 0).mean() < 0.5:
                return None
            q = dict(scale_um=750.0, hp_um=160.0, proud_um=500.0, chan_um=200.0,
                     chan_pct=70, plate_lo_um=100.0, plate_hi_um=500.0)
            return NS.make_features(img, tl["um"], q).get(name)
        return f
    return None


def topmask(a, frac=TOPK):
    """Binarise to the top `frac` of pixels — the detector's actual output."""
    if a is None:
        return None
    thr = np.percentile(a, 100*(1-frac))
    return a >= thr


def jaccard(m1, m2):
    if m1 is None or m2 is None:
        return None
    u = np.logical_or(m1, m2).sum()
    return float(np.logical_and(m1, m2).sum()/u) if u else None


# ---------------------------------------------------------------------------
# 1  STABILITY — the trust standard
# ---------------------------------------------------------------------------
def stability(fn, tile, base):
    """Jaccard overlap of the top-k mask across independent samplings.

    Two axes of variation, per the spec: depth offset (§2.3) and parameter
    jitter. Chance overlap for two independent top-5% masks is ~0.026, so
    anything near that is noise reappearing at random.
    """
    masks = []
    for d in DEPTHS:
        p = dict(base); p["offset"] = d
        try:
            masks.append(("depth%+d" % d, topmask(fn(tile, p))))
        except Exception:
            pass
    rng = np.random.default_rng(4242)
    for i in range(4):
        p = dict(base)
        for k in ("fibre_lo_um", "fibre_hi_um", "neigh_um", "stroke_um"):
            if k in p:
                p[k] = float(p[k])*float(rng.choice([0.85, 1.15]))
        try:
            masks.append((f"jitter{i}", topmask(fn(tile, p))))
        except Exception:
            pass
    masks = [(n, m) for n, m in masks if m is not None]
    if len(masks) < 3:
        return None, None
    js = []
    for i in range(len(masks)):
        for j in range(i+1, len(masks)):
            v = jaccard(masks[i][1], masks[j][1])
            if v is not None:
                js.append(v)
    # how often is a pixel called ink across ALL samplings?
    stack = np.stack([m for _, m in masks]).astype(np.float32)
    consensus = stack.mean(0)
    return (float(np.median(js)) if js else None), consensus


# ---------------------------------------------------------------------------
# 2  DEPTH COHERENCE — uses no labels
# ---------------------------------------------------------------------------
def depth_coherence(fn, tile, base):
    """Per-pixel argmax depth, then agreement with its own neighbourhood.

    The spec's §2.1 in measurable form: ink lies on a surface, so the depth at
    which the response peaks should vary GENTLY across the sheet. If one pixel
    peaks at -9 while its neighbours all peak at +6, that is noise.

    Reported against a shuffled baseline, because a smooth-ish field will
    produce some coherence for free.
    """
    resp = []
    for d in DEPTHS:
        p = dict(base); p["offset"] = d
        try:
            f = fn(tile, p)
        except Exception:
            f = None
        if f is None:
            return None, None
        resp.append(P.z(f))
    R = np.stack(resp)
    dmap = np.argmax(R, axis=0).astype(np.float32)
    r = 6
    local = P.box(dmap, r)
    coh = float(np.mean(np.abs(dmap - local) <= 1.0))
    rng = np.random.default_rng(1)
    sh = dmap.ravel().copy(); rng.shuffle(sh)
    sh = sh.reshape(dmap.shape)
    base_coh = float(np.mean(np.abs(sh - P.box(sh, r)) <= 1.0))
    return coh, base_coh


# ---------------------------------------------------------------------------
# 4  PRECISION at the top 5%
# ---------------------------------------------------------------------------
def precision_at_topk(f, tile, frac=TOPK):
    fb, sub = P._align(f, tile)
    if fb is None:
        return None, None
    tg = sub > 128
    if tg.sum() < 50:
        return None, None
    m = topmask(fb, frac)
    prec = float(tg[m].mean()) if m.sum() else None
    base = float(tg.mean())
    return prec, base


def card(name, n_tiles=10):
    fn = build(name)
    if fn is None:
        print(f"unknown feature: {name}"); return
    base = dict(WV.DEFAULT) if name in WV.WEAVE_NAMES else (
        dict(SC.DEFAULT) if name in SC.SCENT_NAMES else dict(band=8, offset=0))

    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blindp = [t for s in bs for t in by[s]]

    def grab(pool, seed, k, lo=0.03, hi=0.7):
        rng = np.random.default_rng(seed); out = []
        for t in P.warm([pool[i] for i in rng.permutation(len(pool))[:k*3]], verbose=False):
            c = P.crop_coverage(t)
            if c is not None and lo < c < hi:
                tl = P.load_tile(t)
                if tl is not None:
                    out.append(tl)
            if len(out) >= k:
                break
        return out

    t0 = time.time()
    tiles = grab(held, 777, n_tiles)
    blind = grab(blindp, 0, 6)
    negs = [P.load_tile(t) for t in P.warm(P.find_negatives(held, n=8), verbose=False)]
    negs = [t for t in negs if t is not None]

    print("="*70)
    print(f"SCORECARD — {name}")
    print("="*70)
    print(f"{len(tiles)} held-out tiles, {len(negs)} verified-blank, {len(blind)} blind\n")

    # 1 stability
    js, cons = [], None
    for tl in tiles:
        j, c = stability(fn, tl, base)
        if j is not None:
            js.append(j)
            if cons is None:
                cons = c
    jm = float(np.median(js)) if js else None
    chance = TOPK  # expected overlap of two independent top-k masks ~ k
    print(f"1 STABILITY        Jaccard {('%.3f' % jm) if jm else '--'} across "
          f"{len(DEPTHS)} depths + 4 jitters   (chance ~{chance:.3f})")

    # 2 depth coherence
    cohs, bcohs = [], []
    for tl in tiles[:6]:
        c, b = depth_coherence(fn, tl, base)
        if c is not None:
            cohs.append(c); bcohs.append(b)
    cm = float(np.median(cohs)) if cohs else None
    bm = float(np.median(bcohs)) if bcohs else None
    # DROPPED from the verdict. A shuffled baseline is the exact too-easy
    # control this project already got caught by: depth coherence scored 0.970
    # against a 0.276 shuffle, but the BLIND scroll — where the ink was never
    # sampled — scored 0.915. It measures box-filter smoothing, not ink.
    # Printed for the record, never used to pass or fail a candidate.
    print(f"2 DEPTH COHERENCE  {('%.3f' % cm) if cm else '--'} vs shuffled "
          f"{('%.3f' % bm) if bm else '--'}   "
          f"[NOT A CHECK — blind scroll scores 0.915 on this; it measures "
          f"smoothing]")

    # 3 detection
    aucs, nulls, ps = [], [], []
    for tl in tiles:
        f = fn(tl, base)
        if f is None:
            continue
        s = P.auc_vs_ink(f, tl, nulls=40)
        if s:
            aucs.append(s["auc"]); ps.append(s["p"])
            if s["null_median"]:
                nulls.append(s["null_median"])
    am = float(np.median(aucs)) if aucs else None
    nm = float(np.median(nulls)) if nulls else None
    print(f"3 DETECTION        AUC {('%.3f' % am) if am else '--'} vs spatial null "
          f"{('%.3f' % nm) if nm else '--'}   excess "
          f"{('%+.3f' % (am-nm)) if (am and nm) else '--'}   "
          f"{int(100*np.mean(np.array(ps) < 0.05)) if ps else 0}% signif")

    # 4 precision
    pr, bl_ = [], []
    for tl in tiles:
        f = fn(tl, base)
        if f is None:
            continue
        p_, b_ = precision_at_topk(f, tl)
        if p_ is not None:
            pr.append(p_); bl_.append(b_)
    pm = float(np.median(pr)) if pr else None
    pb = float(np.median(bl_)) if bl_ else None
    print(f"4 PRECISION @top5% {('%.3f' % pm) if pm else '--'} vs base rate "
          f"{('%.3f' % pb) if pb else '--'}   lift "
          f"{('x%.2f' % (pm/pb)) if (pm and pb) else '--'}")

    # 5 controls
    ba = []
    for tl in blind:
        f = fn(tl, base)
        if f is None:
            continue
        s = P.auc_vs_ink(f, tl, nulls=1)
        if s:
            ba.append(s["auc"])
    bam = float(np.median(ba)) if ba else None
    nr = P.neg_control(lambda tl: fn(tl, base), negs)
    print(f"5 CONTROLS         blind AUC {('%.3f' % bam) if bam else '--'} "
          f"(chance 0.500)   verified-blank |r| {('%.3f' % nr) if nr else '--'}")

    # 6 evidence
    png = None
    try:
        tl = tiles[0]
        f = fn(tl, base)
        fb, sub = P._align(f, tl)
        def n8(a):
            lo, hi = np.percentile(a, 2), np.percentile(a, 98)
            return np.clip((a-lo)/max(hi-lo, 1e-6)*255, 0, 255).astype(np.uint8)
        S = 340
        sheet = Image.new("RGB", (4*S+30, S), (10, 10, 11))
        det, ink = n8(fb), np.clip(sub, 0, 255).astype(np.uint8)
        cons_img = n8(cons) if cons is not None else np.zeros_like(det)
        if cons_img.shape != det.shape:
            cons_img = np.array(Image.fromarray(cons_img).resize(det.shape[::-1]))
        panels = [Image.fromarray(n8(P.mid_image(tl, 8))).convert("RGB"),
                  Image.fromarray(det).convert("RGB"),
                  Image.fromarray(cons_img).convert("RGB"),
                  Image.fromarray(np.dstack([det, ink, np.zeros_like(det)]))]
        for i, im in enumerate(panels):
            sheet.paste(im.resize((S, S), Image.LANCZOS), (i*(S+10), 0))
        png = os.path.join(OUT, f"{name}_card.png")
        sheet.save(png)
        print(f"6 EVIDENCE         {png}")
        print(f"                   [slice | raw detector | consensus across "
              f"samplings | overlay]")
    except Exception as e:
        print(f"6 EVIDENCE         failed ({e})")

    rec = dict(feature=name, stability=jm, stability_chance=chance,
               depth_coherence=cm, depth_coherence_shuffled=bm,
               auc=am, null=nm, excess=(am-nm) if (am and nm) else None,
               precision_top5=pm, base_rate=pb,
               blind_auc=bam, blank_r=nr, n_tiles=len(tiles), evidence=png)
    json.dump(rec, open(os.path.join(OUT, f"{name}_card.json"), "w"), indent=1)

    print("\n" + "-"*70)
    verdict = []
    if jm is not None and jm < 3*chance:
        verdict.append("UNSTABLE — the mask moves between samplings")
    if am and nm and (am-nm) < 0.08:
        verdict.append("WEAK — barely above its own spatial null")
    if bam and bam > 0.58:
        verdict.append("FIRES ON THE BLIND SCROLL")
    if pm and pb and pm/pb < 1.5:
        verdict.append("LOW PRECISION LIFT")
    if verdict:
        for v in verdict:
            print("  FAIL: " + v)
    else:
        print("  passes every check on this card. NOT a reading — a candidate\n"
              "  worth a fresh draw on new segments and a human look at the\n"
              "  evidence image.")
    print(f"\n{time.time()-t0:.0f}s")
    return rec


if __name__ == "__main__":
    a = sys.argv[1:]
    card(a[0] if a else "weave_fill", int(a[1]) if len(a) > 1 else 10)
