"""VERIFY — try to destroy the alerted candidate.

Every test here can only kill. None can confirm. That asymmetry is the whole
point: the previous alert in this project looked spectacular (d=0.85, z=+6.18)
and was fitting one sheet's damage pattern, and the run before that produced
four candidates at r=+0.42 that were killed by a control which — as it turns
out — was itself broken. Nothing gets believed here without surviving all of
this.

  1 FRESH DRAW    different tiles, different seed. If r collapses it was the
                  draw, not the physics.
  2 PER SCROLL    median per scroll. One scroll carrying the result is not a
                  result. The held-out pool is 55% PHercParis4 by segment
                  count, so a pooled median can be almost entirely one scroll.
  3 ABLATION      does each term earn its place? A three-way combination that
                  dies when any one term is removed is a fit, not a mechanism.
  4 JITTER        the weights are -3.84 / +3.76 / +0.98 — near-equal and
                  opposite, i.e. a DIFFERENCE. Differences can be knife-edge
                  cancellations. Perturb them and see whether this is a
                  plateau or a spike.
  5 CONTROLS      wider verified-blank set and wider blind set than the search
                  used.
  6 EVIDENCE      render it beside the ink map so a human can look.

Usage: python3 verify.py [path_to_alert_json]

METRIC NOTE (2026-07-27): this battery was written against CORRELATION while
the search was switched to AUC. Running a correlation battery on an AUC
candidate compares two different quantities and its "fresh draw r = +0.015"
against a claimed AUC of 0.783 is meaningless as a comparison. Converted to
`pack.auc_vs_ink` throughout so the falsification test measures the same thing
the search optimised. Thresholds below are AUC (0.500 = chance), not r.
"""

import os, sys, json, time
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P
import depth_pca as DP

_argv, sys.argv = sys.argv, [sys.argv[0]]
import nightshift as NS
import rti as RTI
import dogs as D
sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "verify")
os.makedirs(OUT, exist_ok=True)


def load_variant(path=None):
    path = path or os.path.join(HERE, "..", "out", "dogs", "DOGS_ALERT.md")
    txt = open(path).read()
    s = txt.index("```json")+7
    e = txt.index("```", s)
    return json.loads(txt[s:e])


def med_on(V, tiles, gate=(0.02, 0.90)):
    rs, ps, per = [], [], {}
    for t in tiles:
        tile = P.load_tile(t)
        if tile is None:
            continue
        try:
            f = D.feature_map(tile, V)
        except Exception:
            continue
        if f is None:
            continue
        s = P.auc_vs_ink(f, tile, require_cov=gate)
        if s:
            rs.append(s["auc"]); ps.append(s["p"])
            per.setdefault(s["scroll"], []).append(s["auc"])
    if not rs:
        return None
    rs = np.array(rs)
    sign = 1.0 if np.median(rs) > 0 else -1.0
    return dict(median=float(np.median(sign*rs)), n=len(rs),
                frac=float((np.array(ps) < 0.05).mean()),
                per_scroll={k: float(np.median(sign*np.array(v))) for k, v in per.items()},
                sign=sign)


def main(path=None):
    rec = load_variant(path)
    V = rec["variant"]
    print("VERIFYING:", "+".join(V["features"]))
    print(f"  claimed: raw {rec['heldout_median']:+.3f}, blank "
          f"{rec['negative_control']:.3f}, blind {rec['physics_control']:.3f}, "
          f"partial {rec.get('partial_r', float('nan')):.3f}\n")

    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blind_pool = [t for s in bs for t in by[s]]

    # --- 1 FRESH DRAW ------------------------------------------------------
    rng = np.random.default_rng(777)          # NOT a seed any dog used
    fresh = P.warm([held[i] for i in rng.permutation(len(held))[:30]], verbose=False)
    print(f"1 FRESH DRAW ({len(fresh)} tiles, unseen seed)")
    fr = med_on(V, fresh)
    if fr is None:
        print("   no usable tiles — cannot verify"); return
    print(f"   r = {fr['median']:+.3f}  ({fr['frac']*100:.0f}% signif, n={fr['n']})  "
          f"{'PASS' if fr['median'] >= 0.66 else 'FAIL — was the tile draw'}\n")

    # --- 2 PER SCROLL ------------------------------------------------------
    print("2 PER SCROLL")
    for s, v in sorted(fr["per_scroll"].items()):
        print(f"   {s:14s} {v:+.3f}")
    worst = min(fr["per_scroll"].values())
    nsc = len(fr["per_scroll"])
    ok2 = worst >= 0.60 and nsc >= 3          # AUC per scroll, 0.500 = chance
    print(f"   worst {worst:+.3f} across {nsc} scrolls  "
          f"{'PASS' if ok2 else 'FAIL — one scroll carrying it'}\n")

    # --- 3 ABLATION --------------------------------------------------------
    print("3 ABLATION (drop one term at a time)")
    for i, nm in enumerate(V["features"]):
        Q = json.loads(json.dumps(V))
        Q["features"] = [f for j, f in enumerate(V["features"]) if j != i]
        Q["weights"] = [w for j, w in enumerate(V["weights"]) if j != i]
        a = med_on(Q, fresh)
        print(f"   without {nm:14s} r = {'--' if a is None else format(a['median'],'+.3f')}")
    for i, nm in enumerate(V["features"]):
        Q = json.loads(json.dumps(V))
        Q["features"] = [nm]; Q["weights"] = [V["weights"][i]]
        a = med_on(Q, fresh)
        print(f"   {nm:14s} alone  r = {'--' if a is None else format(a['median'],'+.3f')}")
    print()

    # --- 4 JITTER ----------------------------------------------------------
    print("4 JITTER (is this a plateau or a knife edge?)")
    held_j, tried = 0, 0
    jr = np.random.default_rng(5)
    for k in range(10):
        Q = json.loads(json.dumps(V))
        Q["weights"] = [float(w)*float(jr.choice([0.85, 0.92, 1.08, 1.15]))
                        for w in Q["weights"]]
        Q["scale_um"] = float(Q["scale_um"])*float(jr.choice([0.85, 1.15]))
        Q["depth_band"] = int(max(4, Q["depth_band"] + int(jr.choice([-4, -2, 2]))))
        a = med_on(Q, fresh[:16])
        if a:
            tried += 1
            if a["median"] >= 0.66:
                held_j += 1
    frac = held_j/max(tried, 1)
    print(f"   {held_j}/{tried} perturbed neighbours hold above 0.66  "
          f"{'PASS — plateau' if frac >= 0.5 else 'FAIL — knife-edge cancellation'}\n")

    # --- 5 CONTROLS --------------------------------------------------------
    print("5 CONTROLS (wider than the search used)")
    negs = P.warm(P.find_negatives(held, n=12), verbose=False)
    cc = [P.crop_coverage(t) for t in negs]
    nr = P.neg_control(lambda tl: D.feature_map(tl, V), negs)
    print(f"   verified-blank n={len(negs)} (max crop cov "
          f"{max([c for c in cc if c is not None], default=0):.4f})  |r| = "
          f"{'--' if nr is None else format(nr,'.3f')}  "
          f"{'PASS' if nr is not None and nr <= 0.12 else 'FAIL'}")
    blind = P.warm([blind_pool[i] for i in
                    np.random.default_rng(99).permutation(len(blind_pool))[:12]],
                   verbose=False)
    bl = med_on(V, blind)
    print(f"   blind scroll n={0 if bl is None else bl['n']}  |r| = "
          f"{'--' if bl is None else format(abs(bl['median']),'.3f')}  "
          f"{'PASS' if bl is None or abs(bl['median']) <= 0.58 else 'FAIL'}\n")

    # --- 6 EVIDENCE --------------------------------------------------------
    made = 0
    for t in fresh:
        tile = P.load_tile(t)
        if tile is None:
            continue
        try:
            f = D.feature_map(tile, V)
        except Exception:
            continue
        if f is None:
            continue
        s = P.auc_vs_ink(f, tile)
        if not s:
            continue
        def n8(a):
            lo, hi = np.percentile(a, 2), np.percentile(a, 98)
            return np.clip((a-lo)/max(hi-lo, 1e-6)*255, 0, 255).astype(np.uint8)
        S = 420
        sh = Image.new("L", (S*3+20, S), 0)
        sh.paste(Image.fromarray(n8(P.mid_image(tile, 8))).resize((S, S), Image.LANCZOS), (0, 0))
        sh.paste(Image.fromarray(n8(f)).resize((S, S), Image.LANCZOS), (S+10, 0))
        sh.paste(Image.fromarray(np.clip(tile["ink"], 0, 255).astype(np.uint8)).resize((S, S), Image.LANCZOS), (2*S+20, 0))
        p = os.path.join(OUT, f"evidence_{tile['scroll']}_{made}.png")
        sh.save(p)
        made += 1
        if made >= 4:
            break
    print(f"6 EVIDENCE  {made} images in {OUT}  [slice | detector | published ink]\n")

    verdict = dict(fresh=fr["median"], fresh_n=fr["n"], per_scroll=fr["per_scroll"],
                   blank=nr, blind=None if bl is None else abs(bl["median"]),
                   jitter_frac=frac)
    json.dump(verdict, open(os.path.join(OUT, "verdict.json"), "w"), indent=1)

    # AUC scale throughout: 0.500 = chance. The blank control stays on |r|
    # because a verified-blank crop binarises to all zeros and has no AUC.
    survived = (fr["median"] >= 0.66 and ok2 and frac >= 0.5
                and nr is not None and nr <= 0.12
                and (bl is None or abs(bl["median"]) <= 0.58))
    print("="*70)
    print("SURVIVED EVERY TEST" if survived else "KILLED")
    if survived:
        print("Still not a reading. It means a measure tracks published ink across\n"
              "scrolls it was never tuned on, stays quiet on verified-blank sheet\n"
              "and on a scroll whose ink was never sampled, and does not depend on\n"
              "a knife-edge weight. Next: look at the evidence images, then test\n"
              "on an unread scroll.")
    return verdict


if __name__ == "__main__":
    t0 = time.time()
    main(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"{time.time()-t0:.0f}s")
