"""DOGS — the pack. Third-generation search, with the trap welded shut.

WHAT WENT WRONG LAST TIME, IN ONE PARAGRAPH

The first swarm optimised held-out correlation against published ink. It found
candidates at r = +0.44 across held-out segments on three scrolls, 62%
significant, clearing every gate it had. Then the forensic pass ran them on
blank papyrus with no ink on it and they scored |r| = 0.21 to 0.47. They were
not detecting ink. They were detecting papyrus CONDITION — text sits on
well-preserved sheet, so "this sheet looks good" tracks "there is text here"
without any of it being about ink. Every single high scorer did this. The search
was working perfectly; the objective was wrong.

THE FIX, WHICH IS THE ONLY REASON THIS FILE EXISTS

The negative control moves INSIDE the objective:

    score = heldout_median - 1.5 * negative_control_r

Before, the control ran afterwards, as a post-hoc execution. A search will climb
whatever gradient you give it, so putting the control downstream just meant it
climbed into the trap and got killed there, over and over, all night. Now the
trap is part of the landscape and the papyrus-detector family is scored into the
floor by construction. It cannot win. A variant that has not been controlled at
all is charged a pessimistic default, so silence is not rewarded either.

WHAT ELSE IS NEW

The old search could only recombine the eight texture quantities that happened
to get written. Two new families are in the bank:

  RTI      multi-light specular relief, orientation-blind by construction
  PCA      fixed depth-basis projections, the combination-across-depth idea

Nineteen features instead of eight, and the two new families measure things the
texture bank structurally could not.

Usage
    python3 dogs.py --pack 8            launch the pack for 8 hours
    python3 dogs.py --run 8 0           one dog (used by --pack)
"""
import os, sys, json, time, math, subprocess, signal
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P
import depth_pca as DP

# Imported with argv blanked. These modules are also command-line tools and
# read sys.argv at module scope; importing them under this file's argv is how
# the texture bank silently vanished from a launch once already.
_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import nightshift as NS
    HAVE_TEXTURE = True
except Exception as e:
    print(f"WARNING: texture features unavailable ({e})", flush=True)
    HAVE_TEXTURE = False
finally:
    sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get("INK_RUN", os.path.join(HERE, "..", "out", "dogs"))
os.makedirs(RUN, exist_ok=True)
ALERT = os.path.join(RUN, "DOGS_ALERT.md")

# ---- the bar. every clause has to hold. -----------------------------------
# With verified-blank controls the blank term runs ~0.12 rather than the ~0.25
# the broken control reported, so a 0.25 threshold combined with the raw>=0.30
# and blank<=0.10 gates below was unreachable by construction — a run that can
# only ever be silent teaches nothing. The gates do the real work; this is a
# summary threshold and 0.20 is the tightest value consistent with them.
# AUC, NOT CORRELATION.
#
# Correlation against a sparse binary target is dominated by the ~95% of pixels
# that are blank. The positive control settled it: synthetic ink injected at
# 100% of sheet contrast still only reached r = 0.484, so the meter saturates
# far below a perfect detector. Fourteen mechanisms were judged with an
# instrument that cannot move, and under AUC four of them turn out to carry real
# ranking signal.
#
# The score is EXCESS OVER THE SPATIAL NULL, not raw AUC. Shifted targets still
# score ~0.635 on this data because of autocorrelation, so raw AUC flatters
# everything by roughly that much. Excess is the honest effect size.
MIN_EXCESS      = 0.09     # AUC minus its own spatial-null median
MIN_AUC         = 0.66     # raw held-out AUC (0.50 = coin flip)
MAX_BLIND_AUC   = 0.58     # near chance where the ink was never sampled
MIN_FRAC_SIGNIF = 0.40
MIN_SEGS        = 8
MIN_SCROLLS     = 2
# ---------------------------------------------------------------------------

TEXTURE_NAMES = ["sharp", "offaxis", "disorder", "hfenergy", "localsd", "proud",
                 "plate", "chandark"]
ALL_NAMES = (TEXTURE_NAMES if HAVE_TEXTURE else []) + DP.PCA_NAMES
_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import rti as RTI
    ALL_NAMES += RTI.RTI_NAMES
    HAVE_RTI = True
except Exception as e:
    print(f"WARNING: RTI features unavailable ({e})", flush=True)
    HAVE_RTI = False
finally:
    sys.argv = _argv

# The physics bank. Every other feature in this file measures a LEVEL, and the
# literature says the ink is an edge effect plus particulate lead — neither of
# which survives a box filter. See findings/ink-physics.md.
_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import scent as SC
    ALL_NAMES += SC.SCENT_NAMES
    HAVE_SCENT = True
except Exception as e:
    print(f"WARNING: scent features unavailable ({e})", flush=True)
    HAVE_SCENT = False
finally:
    sys.argv = _argv

# Weave-relative bank. Measures ink AGAINST the fibre lattice instead of
# against a flat background — the one framing that survives the finding that
# weave and stroke share a spatial band (335 vs 346 um) and cannot be
# separated by any filter. weave_fill is the best-shaped candidate this
# project has produced: partial r 0.252 > raw 0.135, and 0.036 on the blind
# scroll.
_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import weave as WV
    ALL_NAMES += WV.WEAVE_NAMES
    HAVE_WEAVE = True
except Exception as e:
    print(f"WARNING: weave features unavailable ({e})", flush=True)
    HAVE_WEAVE = False
finally:
    sys.argv = _argv


# Depth-column bank. Per-pixel profile shape with the face located PER PIXEL,
# so sheet warp cannot smear it. This is the only bank that does not begin by
# flattening the stack into a 2D image — every other feature in this file does,
# which is exactly what the build brief warns against.
_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import column as CL
    ALL_NAMES += CL.COLUMN_NAMES
    HAVE_COLUMN = True
except Exception as e:
    print(f"WARNING: column features unavailable ({e})", flush=True)
    HAVE_COLUMN = False
finally:
    sys.argv = _argv


# The pack. Named because twelve numbered workers produce unreadable logs, and
# because it is easier to ask "what did Pliny find" than "what did w7 find".
# Pliny the Elder died at Vesuvius; Philo is for Philodemus, whose library this
# is; Argos is Odysseus' dog, who alone recognised him after twenty years.
DOG_NAMES = ["Argos", "Pliny", "Livia", "Cerberus", "Juno", "Rufus",
             "Nero", "Vesta", "Remus", "Scipio", "Bruta", "Philo"]


def dog_name(wid):
    return DOG_NAMES[wid % len(DOG_NAMES)] + ("" if wid < len(DOG_NAMES)
                                              else f"-{wid//len(DOG_NAMES)+1}")


def _sampling_weights():
    """Not uniform. The level-based bank (density, brightness, variance,
    orientation) has now failed fourteen times, and the research in
    findings/ink-physics.md says the ink is an edge effect at the ink/fibre
    boundary measured against the fibre lattice. Uniform sampling over 29
    features spends two thirds of the run re-testing the hypothesis that is
    already dead, so the physics and weave banks get the draws.

    weave_period is deliberately DOWN-weighted: it is the papyrus structure
    itself, present as a trap for candidates that lean on it.
    """
    w = []
    for n in ALL_NAMES:
        if HAVE_COLUMN and n in CL.COLUMN_NAMES:
            w.append(4.5)
        elif HAVE_WEAVE and n in WV.WEAVE_NAMES:
            w.append(0.6 if n == "weave_period" else 5.0)
        elif HAVE_SCENT and n in SC.SCENT_NAMES:
            w.append(3.5)
        elif n.startswith("pca_") or n.startswith("rti_"):
            w.append(1.2)
        else:
            w.append(0.8)
    w = np.array(w, float)
    return w/w.sum()


WEIGHTS = _sampling_weights()


def sample_variant(rng):
    n = int(rng.integers(1, 4))
    names = [str(x) for x in rng.choice(ALL_NAMES, size=n, replace=False, p=WEIGHTS)]
    return {
        "features": names,
        "weights": [float(rng.choice([1.0, 0.7, 0.5, -0.5, -0.7, -1.0])) for _ in names],
        "scale_um": float(rng.choice([250, 400, 600, 750, 1000, 1500])),
        "hp_um": float(rng.choice([60, 100, 160, 250])),
        "proud_um": float(rng.choice([300, 500, 900])),
        "chan_um": float(rng.choice([100, 200, 350])),
        "chan_pct": int(rng.choice([60, 70, 80, 88])),
        "plate_lo_um": 100.0,
        "plate_hi_um": float(rng.choice([300, 500, 800])),
        "depth_band": int(rng.choice([4, 8, 14])),
        # RTI parameters
        "lo_um": float(rng.choice([100, 150, 250, 400])),
        "hi_um": float(rng.choice([800, 1200, 2000])),
        "unsharp_um": float(rng.choice([300, 600, 1000])),
        "gain": float(rng.choice([1.5, 3.0, 5.0])),
        "exponent": float(rng.choice([15, 40, 80])),
        "elev_deg": float(rng.choice([10, 18, 30])),
        "n_lights": 12,
        # physics bank. stroke_um is centred on the MEASURED hand (0.35 mm)
        # rather than swept blindly, because that width is known.
        "stroke_um": float(rng.choice([200, 275, 350, 450, 600])),
        "fringe_um": float(rng.choice([15, 25, 40, 70])),
        "tail_pct": float(rng.choice([99.0, 99.5, 99.9])),
        "void_pct": float(rng.choice([1.0, 2.0, 5.0])),
        # weave bank. The fibre corrugation sits near 335 um; the stroke near
        # 346. The band is swept around both because the point is not to
        # separate them by scale — that already failed — but to model the
        # lattice and measure the anomaly.
        "fibre_lo_um": float(rng.choice([150, 200, 260, 320])),
        "fibre_hi_um": float(rng.choice([450, 600, 800, 1100])),
        "neigh_um": float(rng.choice([900, 1500, 2400, 4000])),
        "crest_pct": float(rng.choice([50, 65, 80])),
        # THE DEPTH AXIS. Ink is a surface layer, so if it is anywhere it is at
        # a particular depth. Every previous run averaged a band centred on the
        # sheet peak, which cannot express that at all.
        "offset": int(rng.choice([-15, -12, -9, -6, -3, 0, 3, 6, 9, 12, 15])),
        # depth-column parameters
        "col_span": int(rng.choice([14, 20, 26])),
        "col_smooth": float(rng.choice([1.0, 1.5, 3.0])),
        "col_shoulder": int(rng.choice([2, 3, 5, 8])),
    }


def mutate(V, rng):
    """Hill-climb around something that worked. Keeps the feature set, jitters
    the parameters — a real effect should be a plateau, not a spike."""
    Q = json.loads(json.dumps(V))
    for k in ["scale_um", "hp_um", "lo_um", "hi_um", "unsharp_um", "gain", "exponent"]:
        if rng.random() < 0.4:
            Q[k] = float(Q[k]) * float(rng.choice([0.7, 0.85, 1.2, 1.5]))
    if rng.random() < 0.3:
        Q["depth_band"] = int(max(3, Q["depth_band"] + rng.choice([-4, -2, 2, 4])))
    if rng.random() < 0.45:
        Q["offset"] = int(np.clip(Q.get("offset", 0) + rng.choice([-6, -3, 3, 6]), -18, 18))
    if rng.random() < 0.25:
        # Clamped. Unbounded multiplicative drift let weights reach -3.84/+3.76
        # — near-equal and opposite, i.e. a razor-thin difference between two
        # z-scored maps. That is the shape of a knife-edge cancellation, and
        # the one candidate built that way died 0/10 under an 8% jitter.
        # Genuine contrasts are expressible within +/-1.5.
        Q["weights"] = [float(np.clip(float(w)*float(rng.choice([0.7, 1.0, 1.4])),
                                      -1.5, 1.5)) for w in Q["weights"]]
    if rng.random() < 0.2 and len(Q["features"]) < 3:
        cand = [n for n in ALL_NAMES if n not in Q["features"]]
        p = np.array([WEIGHTS[ALL_NAMES.index(n)] for n in cand], float)
        Q["features"] = Q["features"] + [str(rng.choice(cand, p=p/p.sum()))]
        Q["weights"] = Q["weights"] + [float(rng.choice([1.0, 0.7, -0.7, -1.0]))]
    return Q


# ---------------------------------------------------------------------------
_FAM_KEYS = {
    "texture": ("scale_um", "hp_um", "proud_um", "chan_um", "chan_pct",
                "plate_lo_um", "plate_hi_um", "depth_band", "offset"),
    "rti": ("depth_band", "lo_um", "hi_um", "unsharp_um", "gain", "exponent",
            "elev_deg", "n_lights", "offset"),
    "scent": ("stroke_um", "fringe_um", "depth_band", "tail_pct", "void_pct",
              "offset"),
    "weave": ("depth_band", "fibre_lo_um", "fibre_hi_um", "neigh_um",
              "crest_pct", "offset"),
    "column": ("col_span", "col_smooth", "col_shoulder"),
}
_fam_cache = {}


def _fam(tile, V, family, compute):
    """Cache a whole feature FAMILY per (tile, family, its own parameters).

    Families compute all their maps in one pass, and the hill-climber changes
    one parameter at a time — so the jitter, confirmation and control stages of
    a single candidate re-request identical maps repeatedly. Without this the
    pack ran at 7.7 variants/minute across twelve workers.

    Keyed on ONLY the parameters that family actually reads, so an RTI tweak
    does not invalidate the weave maps.
    """
    key = (tile["seg"], family,
           tuple(round(float(V.get(k, 0)), 4) if isinstance(V.get(k, 0), (int, float))
                 else V.get(k) for k in _FAM_KEYS[family]))
    hit = _fam_cache.get(key)
    if hit is not None:
        return hit
    out = compute()
    if len(_fam_cache) > 24:
        _fam_cache.clear()
    _fam_cache[key] = out
    return out


def feature_map(tile, V):
    """Compute only the families the variant actually asks for. A variant using
    one PCA component must not pay for a 12-light RTI sweep."""
    want = set(V["features"])
    F = {}
    if HAVE_TEXTURE and (want & set(TEXTURE_NAMES)):
        def _tex():
            img = P.mid_image(tile, int(V["depth_band"]), int(V.get("offset", 0)))
            if (img > 0).mean() < 0.5:
                return {}
            return NS.make_features(img, tile["um"], V)
        t = _fam(tile, V, "texture", _tex)
        if not t:
            return None
        F.update(t)
    if want & set(DP.PCA_NAMES):
        F.update(DP.pca_features(tile))
    if HAVE_COLUMN and (want & set(CL.COLUMN_NAMES)):
        F.update(_fam(tile, V, "column", lambda: CL.column_features(tile, dict(
            span=int(V.get("col_span", 20)),
            smooth=float(V.get("col_smooth", 1.5)),
            shoulder=int(V.get("col_shoulder", 3))))))
    if HAVE_WEAVE and (want & set(WV.WEAVE_NAMES)):
        F.update(_fam(tile, V, "weave", lambda: WV.weave_features(tile, dict(
            band=int(V["depth_band"]),
            fibre_lo_um=V.get("fibre_lo_um", 200.0),
            fibre_hi_um=V.get("fibre_hi_um", 600.0),
            neigh_um=V.get("neigh_um", 1500.0),
            crest_pct=V.get("crest_pct", 65.0),
            offset=int(V.get("offset", 0))))))
    if HAVE_SCENT and (want & set(SC.SCENT_NAMES)):
        F.update(_fam(tile, V, "scent", lambda: SC.scent_features(tile, dict(
            stroke_um=V.get("stroke_um", SC.STROKE_UM),
            fringe_um=V.get("fringe_um", 40.0),
            band=int(V["depth_band"]),
            tail_pct=V.get("tail_pct", 99.5),
            void_pct=V.get("void_pct", 2.0),
            tail_band=20,
            offset=int(V.get("offset", 0))))))
    if HAVE_RTI and (want & set(RTI.RTI_NAMES)):
        F.update(_fam(tile, V, "rti", lambda: RTI.rti_features(tile, dict(
            band=int(V["depth_band"]), lo_um=V["lo_um"], hi_um=V["hi_um"],
            unsharp_um=V["unsharp_um"], gain=V["gain"], exponent=V["exponent"],
            elev_deg=V["elev_deg"], n_lights=int(V["n_lights"])))))
    out = None
    for nm, w in zip(V["features"], V["weights"]):
        if nm not in F:
            return None
        t = w*P.z(F[nm])
        out = t if out is None else out + t
    if out is None or not np.isfinite(out).all():
        return None
    return out


def evaluate(V, tiles, nulls=40):
    """AUC with a spatial null. See the bar block above for why not correlation."""
    res = []
    for t in tiles:
        tile = P.load_tile(t) if isinstance(t, dict) else t
        if tile is None:
            continue
        try:
            f = feature_map(tile, V)
        except Exception:
            continue
        if f is None:
            continue
        s = P.auc_vs_ink(f, tile, nulls=nulls)
        if s:
            res.append(s)
    return res


def run_dog(hours, wid):
    t0 = time.time()
    NAME = dog_name(wid)
    log = open(os.path.join(RUN, f"dogs_w{wid}.jsonl"), "a")
    rng = np.random.default_rng(1000 + wid*17 + int(t0) % 9973)

    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    tune = [t for s in ts for t in by[s]]
    held = [t for s in hs for t in by[s]]
    blind_pool = [t for s in bs for t in by[s]]
    print(f"[{NAME}] tune {ts} | held {hs}", flush=True)
    print(f"[{NAME}] physics control {bs} "
          f"({', '.join(f'{s}={P.voxels_through_ink(um[s]):.1f}vox' for s in bs)})",
          flush=True)

    # Each dog gets its OWN tile draw, so a lucky draw cannot be mistaken for a
    # real effect when several dogs agree. But the draws come from a shared,
    # deterministic pool: ten dogs drawing freely from 200 segments would pull
    # ~300 distinct tiles and blow out both the disk cache and the network,
    # while every dog waits on cold fetches. Bounded pool, independent draws.
    held_full = list(held)          # controls are chosen from the WIDEST pool
    pool = np.random.default_rng(0)
    tune = [tune[i] for i in pool.permutation(len(tune))[:16]]
    held = [held[i] for i in pool.permutation(len(held))[:64]]

    # NESTED VALIDATION. The previous design hill-climbed against ONE fixed
    # held-out draw for the whole run. After 5,759 variants that set was no
    # longer held out — it was training data, and the search duly produced a
    # knife-edge weight combination scoring +0.392 on it that collapsed to
    # +0.053 on a fresh draw. Selection on the validation set manufactures a
    # winner every time, given enough iterations.
    #
    # So: SELECT on a rotating draw (so no single draw can be memorised), and
    # CONFIRM on a disjoint set of segments that never influences selection at
    # all. Nothing can alert without holding on segments it was never chosen
    # against.
    confirm_pool = held[:20]
    select_pool = held[20:]

    tune_pick = list(rng.choice(tune, size=min(8, len(tune)), replace=False))
    held_pick = list(rng.choice(select_pool, size=min(24, len(select_pool)), replace=False))
    tune_pick = P.warm(tune_pick, verbose=(wid == 0))
    held_pick = P.warm(held_pick, verbose=(wid == 0))
    select_pool = P.warm(select_pool, verbose=(wid == 0))
    confirm_pick = P.warm(confirm_pool, verbose=(wid == 0))
    negs = P.warm(P.find_negatives(held_full, n=8), verbose=(wid == 0))
    blind = P.warm([blind_pool[i] for i in
                    np.random.default_rng(0).permutation(len(blind_pool))[:6]],
                   verbose=(wid == 0)) if blind_pool else []
    print(f"[{NAME}] {len(tune_pick)} tune, {len(held_pick)} held-out, "
          f"{len(negs)} blank-control, {len(blind)} physics-control tiles", flush=True)
    if len(held_pick) < MIN_SEGS or len(negs) < 4:
        print(f"[{NAME}] not enough tiles (need >={MIN_SEGS} held-out and >=4 "
              f"controls); stopping", flush=True)
        return

    best = None
    n = 0
    deadline = t0 + hours*3600
    ROTATE = 120        # variants between re-draws of the selection set
    while time.time() < deadline:
        n += 1
        # rotate the selection tiles so no single draw can be fitted
        if n % ROTATE == 0 and len(select_pool) > 24:
            held_pick = list(rng.choice(select_pool, size=24, replace=False))
            best = None          # a best chosen against the old draw is void
            print(f"[{NAME}] rotated selection tiles at variant {n}", flush=True)

        V = mutate(best["variant"], rng) if (best and rng.random() < 0.35) else sample_variant(rng)

        tr = evaluate(V, tune_pick, nulls=1)
        if len(tr) < 3:
            continue
        tune_med = float(np.median([x["auc"] for x in tr]))
        if tune_med < 0.55:          # 0.50 is a coin flip
            log.write(json.dumps({"variant": V, "tune_median": tune_med,
                                  "stage": "rejected"})+"\n"); log.flush()
            continue

        # EARLY ABORT. Most variants die; paying 24 tiles to learn that is the
        # single biggest waste in the run. Screen on a third first, and only
        # buy the full draw for something that could plausibly clear the bar.
        # The full draw is still what gets SCORED — this only skips hopeless
        # variants, so it cannot inflate a result.
        # Threshold must sit ABOVE the spatial null, not below it. The first
        # version used 0.60 while the null on this data is ~0.62, so every
        # variant cleared the screen, nothing was ever aborted, and the extra
        # 8 tile evaluations made the pack SLOWER. Measured: 0 screened in 5
        # minutes. 0.64 actually discriminates without cutting anything that
        # could reach MIN_AUC=0.66.
        screen = evaluate(V, held_pick[:8], nulls=1)
        if len(screen) >= 5 and float(np.median([x["auc"] for x in screen])) < 0.64:
            log.write(json.dumps({"variant": V, "screen": float(np.median(
                [x["auc"] for x in screen])), "stage": "screened"})+"\n"); log.flush()
            continue

        hr = evaluate(V, held_pick)
        if len(hr) < MIN_SEGS:
            continue
        aucs = np.array([x["auc"] for x in hr])
        ps = np.array([x["p"] for x in hr])
        nulls_ = np.array([x["null_median"] for x in hr if x["null_median"]])
        med = float(np.median(aucs))
        # EXCESS over the variant's own spatial null. Shifted targets score
        # ~0.635 on this data purely from autocorrelation, so raw AUC flatters
        # everything by about that much and is not an effect size.
        null_med = float(np.median(nulls_)) if len(nulls_) else 0.5
        excess = med - null_med
        frac = float((ps < 0.05).mean())
        nsc = len({x["scroll"] for x in hr})

        # ---- THE CONTROLS, INSIDE THE LOOP --------------------------------
        # Only paid for when a variant could plausibly win.
        nr = br = None
        if med >= 0.62:
            nr = P.neg_control(lambda tl: feature_map(tl, V), negs)
            # PHYSICS CONTROL: the blind scroll carries text but its scan never
            # sampled the ink layer. A detector must be near chance there.
            if blind:
                bres = evaluate(V, blind, nulls=1)
                if len(bres) >= 3:
                    br = float(np.median([x["auc"] for x in bres]))
        final = excess
        if br is not None:
            final -= 1.5*max(0.0, br - 0.55)
        else:
            final -= 0.05           # unmeasured control is never free
        if nr is not None:
            final -= 0.5*max(0.0, nr - 0.12)

        # partial correlation, recorded but NOT optimised: does the feature
        # explain ink beyond sheet brightness/contrast/coherence/curvature?
        pr = None
        if med >= 0.18:
            pv = []
            for t in held_pick[:8]:
                tile = P.load_tile(t)
                if tile is None:
                    continue
                try:
                    f = feature_map(tile, V)
                except Exception:
                    continue
                if f is None:
                    continue
                s = P.score_partial(f, tile, nulls=12)
                if s:
                    pv.append(abs(s["r"]))
            pr = float(np.median(pv)) if len(pv) >= 3 else None
        # -------------------------------------------------------------------

        rec = {"variant": V, "tune_median": tune_med, "heldout_median": med,
               "null_median": null_med, "excess": excess,
               "frac_signif": frac, "n_heldout": len(hr), "n_scrolls": nsc,
               "negative_control": nr, "physics_control": br, "partial_r": pr,
               "penalised": final, "stage": "tested", "t": round(time.time()-t0)}
        log.write(json.dumps(rec)+"\n"); log.flush()

        if best is None or final > best["penalised"]:
            best = rec
            best["dog"] = NAME
            json.dump(best, open(os.path.join(RUN, f"dogs_best_w{wid}.json"), "w"), indent=1)
            print(f"[{NAME}] {n:5d} excess {final:+.3f} "
                  f"(AUC {med:.3f} vs null {null_med:.3f}, blank "
                  f"{('%.3f' % nr) if nr is not None else '--'}, blind "
                  f"{('%.3f' % br) if br is not None else '--'}, "
                  f"{frac*100:.0f}% signif, {nsc} scrolls, depth {V.get('offset',0):+d}) "
                  f"{'+'.join(V['features'])}", flush=True)

        gates = (final >= MIN_EXCESS and med >= MIN_AUC
                 and (br is None or br <= MAX_BLIND_AUC)
                 and frac >= MIN_FRAC_SIGNIF and len(hr) >= MIN_SEGS
                 and nsc >= MIN_SCROLLS)

        if gates:
            # CONFIRMATION on segments that never influenced selection, plus a
            # jitter check. The previous alert cleared every gate above and
            # then scored +0.053 on a fresh draw and 0/10 under jitter. Both
            # are now preconditions for alerting, not post-hoc forensics.
            cres = evaluate(V, confirm_pick)
            cmed = float(np.median([x["auc"] for x in cres])) if len(cres) >= 6 else None
            jr_ = np.random.default_rng(4242)
            held_j = tried_j = 0
            # Use the WHOLE selection draw and a proportional quorum. The first
            # version demanded 6 scored tiles out of the first 10, which on a
            # thin draw was never met, so tried_j stayed 0, jfrac was 0/1, and
            # every candidate failed the jitter gate for a bookkeeping reason
            # rather than a scientific one. An unreachable gate is the same bug
            # as an unreachable bar.
            quorum = max(4, len(held_pick)//3)
            for _ in range(6):
                Q = json.loads(json.dumps(V))
                Q["weights"] = [float(w)*float(jr_.choice([0.9, 1.1])) for w in Q["weights"]]
                jres = evaluate(Q, held_pick, nulls=1)
                if len(jres) >= quorum:
                    tried_j += 1
                    if float(np.median([x["auc"] for x in jres])) >= 0.5 + 0.6*(med-0.5):
                        held_j += 1
            jfrac = (held_j/tried_j) if tried_j else -1.0   # -1 = never measured
            rec["confirm_median"] = cmed
            rec["jitter_frac"] = jfrac
            log.write(json.dumps({**rec, "stage": "gated"})+"\n"); log.flush()
            if cmed is None or cmed < MIN_AUC - 0.03 or jfrac < 0.5:
                why = ("confirmation set" if (cmed is None or cmed < MIN_AUC - 0.03)
                       else ("jitter never measured" if jfrac < 0 else "jitter"))
                print(f"[{NAME}] gates cleared but CONFIRMATION failed on {why} "
                      f"(confirm {'--' if cmed is None else format(cmed,'.3f')}, "
                      f"jitter {held_j}/{tried_j}) — not a finding", flush=True)
                gates = False

        if gates:
            with open(os.path.join(RUN, "BONE.md"), "w") as f:
                f.write(f"# {NAME} GETS THE BONE\n\n"
                        f"{NAME} found the first candidate to clear every gate WITH both "
                        f"controls subtracted, hold on a confirmation set it was never "
                        f"selected against, and survive weight jitter.\n\n"
                        f"```json\n{json.dumps(rec, indent=1)}\n```\n\n"
                        f"Still not a reading. Run `python3 verify.py "
                        f"{os.path.join(RUN,'BONE.md')}` before saying anything out loud.\n")
            with open(ALERT, "w") as f:
                f.write(f"# DOGS ALERT — {NAME}\n\nA variant cleared the bar WITH the negative "
                        "control already subtracted.\n\n")
                f.write("```json\n"+json.dumps(rec, indent=1)+"\n```\n\n")
                f.write(f"confirmation set (never used for selection) r = "
                        f"{rec.get('confirm_median'):+.3f}\n"
                        f"jitter survival = {rec.get('jitter_frac'):.2f}\n"
                        f"raw held-out r = {med:+.3f}\n"
                        f"blank papyrus |r| = {nr:.3f}\n"
                        f"blind scroll |r| = {'--' if br is None else format(br,'.3f')}"
                        "   (PHerc0172, 1.9 voxels through the ink layer)\n"
                        f"penalised = {final:+.3f}\n\n"
                        "This is the first thing in this project to score well on ink "
                        "while staying quiet on blank sheet. Still NOT a reading.\n\n"
                        "Next: fresh tile draw, per-scroll breakdown, parameter jitter,\n"
                        "and look at the evidence image before believing any of it.\n")
            print(f"\n[w{wid}] *** ALERT — see {ALERT} ***\n", flush=True)
            return

        if n % 25 == 0:
            print(f"[{NAME}] … {n} variants, {(time.time()-t0)/60:.0f} min, "
                  f"best penalised {best['penalised'] if best else 0:+.3f}", flush=True)

    print(f"[{NAME}] done: {n} variants, best penalised "
          f"{best['penalised'] if best else 0:+.3f}", flush=True)


BONE = os.path.join(RUN, "BONE.md")
DEADLINE_FILE = os.path.join(RUN, "deadline.json")


def _spawn_dog(wid, remaining_hours):
    lf = open(os.path.join(RUN, f"dogs_w{wid}.log"), "a")
    return subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--run",
         f"{remaining_hours:.3f}", str(wid)],
        stdout=lf, stderr=lf, cwd=HERE)


def herd(nw):
    """The supervisor. Every previous run died the same way: the dogs were
    children of whatever terminal or session launched them, so when that ended
    — or the laptop rebooted — the whole pack went down silently, twice with a
    live lead on the board. This process is detached (its own session), spawns
    the dogs as ITS children, holds off idle sleep itself, respawns any dog
    that dies with time on the clock, and runs the falsification battery the
    moment a bone lands instead of waiting for a human to notice the file."""
    meta = json.load(open(DEADLINE_FILE))
    dl = meta["deadline"]
    subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    log = open(os.path.join(RUN, "herd.log"), "a")

    def note(m):
        log.write(time.strftime("%F %T ") + m + "\n")
        log.flush()

    def remaining():
        return (dl - time.time()) / 3600

    procs, births, strikes = {}, {}, {}
    for i in range(nw):
        procs[i] = _spawn_dog(i, remaining())
        births[i] = time.time()
        time.sleep(1.5)
    json.dump({**{str(i): p.pid for i, p in procs.items()}, "herd": os.getpid()},
              open(os.path.join(RUN, "pids.json"), "w"))
    note(f"herding {nw} dogs until "
         f"{time.strftime('%F %T', time.localtime(dl))} ({remaining():.1f}h)")

    seen_bone = os.path.getmtime(BONE) if os.path.exists(BONE) else 0
    while time.time() < dl:
        time.sleep(30)
        # A bone nobody verifies is not a gate — the specks alert sat
        # unexecuted for two hours. The battery now runs itself.
        if os.path.exists(BONE) and os.path.getmtime(BONE) > seen_bone:
            seen_bone = os.path.getmtime(BONE)
            ts = time.strftime("%Y%m%d-%H%M")
            note(f"BONE at {ts} — running verify.py")
            try:
                subprocess.run(["osascript", "-e",
                                'display notification "verify.py is running on it now" '
                                'with title "DOGS: bone found"'], timeout=10)
            except Exception:
                pass
            vpath = os.path.join(RUN, f"verify-{ts}.log")
            with open(vpath, "w") as vlog:
                try:
                    subprocess.run([sys.executable, os.path.join(HERE, "verify.py"),
                                    BONE], stdout=vlog, stderr=vlog, cwd=HERE,
                                   timeout=3*3600)
                except Exception as e:
                    vlog.write(f"\nverify battery did not finish: {e}\n")
            note(f"verify done -> {vpath}")
            try:
                subprocess.run(["osascript", "-e",
                                f'display notification "read {vpath}" '
                                'with title "DOGS: verify finished"'], timeout=10)
            except Exception:
                pass
        for i, p in list(procs.items()):
            if p.poll() is None:
                continue
            age = time.time() - births[i]
            if age < 180:
                strikes[i] = strikes.get(i, 0) + 1
                if strikes[i] >= 2:
                    note(f"w{i} died twice within 3 min of spawn — leaving it down, "
                         f"read dogs_w{i}.log")
                    del procs[i]
                    continue
            if remaining() > 0.25:
                note(f"w{i} exited after {age/60:.0f} min — respawning "
                     f"with {remaining():.1f}h left")
                procs[i] = _spawn_dog(i, remaining())
                births[i] = time.time()
            else:
                del procs[i]
    note("deadline reached; herd done")


def _start_herd(nw):
    sup = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--herd", str(nw)],
        stdout=subprocess.DEVNULL, stderr=open(os.path.join(RUN, "herd.log"), "a"),
        cwd=HERE, start_new_session=True)
    return sup.pid


def resume():
    """After a reboot: one command, picks up whatever time is left."""
    if not os.path.exists(DEADLINE_FILE):
        print("no deadline.json — nothing to resume; use --pack")
        return
    meta = json.load(open(DEADLINE_FILE))
    rem = (meta["deadline"] - time.time()) / 3600
    if rem < 0.25:
        print(f"deadline passed ({-rem:.1f}h ago) — start fresh with --pack")
        return
    try:
        pids = json.load(open(os.path.join(RUN, "pids.json")))
        os.kill(int(pids.get("herd", -1)), 0)
        print(f"herd already alive (pid {pids['herd']}) — nothing to do")
        return
    except (OSError, ValueError, FileNotFoundError, KeyError):
        pass
    pid = _start_herd(int(meta.get("nw", 12)))
    print(f"resumed: herd pid {pid}, {rem:.1f}h remaining")


def launch(hours, nw=None):
    nw = nw or max(2, (os.cpu_count() or 4) - 2)
    if not os.path.exists(DP.BASIS):
        print("no depth basis yet — fitting it first (needed by the PCA features)")
        DP.fit_basis()
    print(f"\nreleasing {nw} dogs for {hours}h")
    print(f"bar: AUC-excess >= {MIN_EXCESS}, AUC >= {MIN_AUC}, blind <= {MAX_BLIND_AUC}, "
          f">={int(MIN_FRAC_SIGNIF*100)}% signif, >={MIN_SEGS} segs, >={MIN_SCROLLS} scrolls")
    print(f"feature bank: {len(ALL_NAMES)} features "
          f"({len(TEXTURE_NAMES) if HAVE_TEXTURE else 0} texture, "
          f"{len(DP.PCA_NAMES)} pca, {len(RTI.RTI_NAMES) if HAVE_RTI else 0} rti, "
          f"{len(SC.SCENT_NAMES) if HAVE_SCENT else 0} scent, "
          f"{len(WV.WEAVE_NAMES) if HAVE_WEAVE else 0} weave, "
          f"{len(CL.COLUMN_NAMES) if HAVE_COLUMN else 0} column)")
    # An unattended 12-hour run that quietly lost a third of its search space is
    # worse than no run, because the negative result would be believed.
    if not (HAVE_TEXTURE and HAVE_RTI and HAVE_COLUMN and HAVE_WEAVE and HAVE_SCENT):
        print("\nABORT: feature bank incomplete — fix the import above before launching.\n"
              "       (override deliberately with FORCE=1 in the environment)")
        if os.environ.get("FORCE") != "1":
            return
    json.dump({"deadline": time.time() + hours*3600, "nw": nw,
               "started": time.time()}, open(DEADLINE_FILE, "w"))
    pid = _start_herd(nw)
    print(f"logs: {RUN}")
    print(f"herd pid {pid} — detached; closing this terminal or session cannot kill it")
    print("caffeinate is the herd's child; idle sleep is held off for the whole run")
    print(f"\nwatch:  tail -f {os.path.join(RUN,'dogs_w0.log')}")
    print(f"herd:   tail -f {os.path.join(RUN,'herd.log')}")
    print(f"alert:  ls {ALERT}")
    print("after a reboot:  python3 dogs.py --resume")


def scoreboard():
    """Who is ahead, and what each dog is carrying."""
    import glob
    rows = []
    for f in sorted(glob.glob(os.path.join(RUN, "dogs_best_w*.json"))):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        wid = int(f.split("_w")[-1].split(".")[0])
        rows.append((r.get("dog", dog_name(wid)), r))
    counts = {}
    for f in glob.glob(os.path.join(RUN, "dogs_w*.jsonl")):
        wid = int(f.split("_w")[-1].split(".")[0])
        try:
            counts[dog_name(wid)] = sum(1 for _ in open(f))
        except Exception:
            pass
    if not rows:
        print("no dog has found anything worth writing down yet")
        return
    rows.sort(key=lambda x: -x[1]["penalised"])
    bone = os.path.join(RUN, "BONE.md")
    print(f"{'dog':10s} {'excess':>8s} {'AUC':>7s} {'null':>7s} {'blind':>7s} "
          f"{'depth':>6s} {'tried':>6s}  scent")
    print("-"*78)
    for i, (name, r) in enumerate(rows):
        g = lambda k: "--" if r.get(k) is None else f"{r[k]:.3f}"
        lead = "*" if i == 0 else " "
        print(f"{lead}{name:9s} {r['penalised']:+8.3f} {r['heldout_median']:7.3f} "
              f"{r.get('null_median', float('nan')):7.3f} {g('physics_control'):>7s} "
              f"{r['variant'].get('offset', 0):+6d} {counts.get(name, 0):6d}  "
              f"{'+'.join(r['variant']['features'])}")
    print(f"\nbar: AUC-excess >= {MIN_EXCESS}, AUC >= {MIN_AUC}, blind AUC <= {MAX_BLIND_AUC}")
    print("BONE CLAIMED — see " + bone if os.path.exists(bone)
          else "no bone yet. nothing has cleared the bar.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--scoreboard":
        scoreboard()
    elif a and a[0] == "--run":
        run_dog(float(a[1]), int(a[2]))
    elif a and a[0] == "--herd":
        herd(int(a[1]))
    elif a and a[0] == "--resume":
        resume()
    else:
        launch(float(a[1]) if len(a) > 1 else 8.0,
               int(a[2]) if len(a) > 2 else None)
