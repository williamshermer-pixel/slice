"""FORENSICS — the second shift. Scouts find, forensics tries to destroy.

The swarm searches and moves on. This watches what it writes, picks up anything
above a lower threshold than the alert bar, and attacks it. Every test here is a
FALSIFICATION test: none of them can strengthen a candidate, they can only kill
it. That asymmetry is deliberate. A team that could confirm its own findings
would just manufacture confidence at 4am, which is exactly the failure this whole
night has been about.

Five tests, cheapest and deadliest first:

  1 NEGATIVE CONTROL   run it where there is no ink. A real detector goes quiet.
                       One that has learned "papyrus" lights up everywhere.
  2 FRESH HELD-OUT     new tiles it has never seen. If r collapses, it was the
                       tile draw, not the physics.
  3 PER-SCROLL         median per scroll, not pooled. One scroll carrying the
                       whole result is not a result.
  4 STABILITY          jitter the parameters. A sharp spike is noise; a broad
                       plateau is a real effect that does not care about the
                       third decimal place.
  5 EVIDENCE           render score map beside ink map, so a human can look.

Only a candidate that survives all five gets announced. Everything else is
written to the verdict log with the reason it died.

Runs alongside the swarm; reads swarm_w*.jsonl, writes verdicts/.
"""
import json, os, sys, time, glob
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nightshift as NS

HERE = os.path.dirname(os.path.abspath(__file__))
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
PICKUP_R = 0.18                      # investigate near-misses too
VERDICTS = os.path.join(HERE, "verdicts")
ALERT = os.path.join(HERE, "FORENSIC_ALERT.md")
SEEN = os.path.join(HERE, "forensics_seen.json")
os.makedirs(VERDICTS, exist_ok=True)

# thresholds a survivor must meet
NEG_MAX = 0.12          # negative control must stay below this
FRESH_MIN = 0.20        # fresh held-out draw must hold at least this
SCROLL_MIN = 0.12       # every contributing scroll must clear this
STABLE_FRAC = 0.5       # half of jittered neighbours must stay above FRESH_MIN


def load_seen():
    try:
        return set(json.load(open(SEEN)))
    except Exception:
        return set()


def save_seen(s):
    json.dump(sorted(s), open(SEEN, "w"))


def key_of(rec):
    v = rec["variant"]
    return json.dumps([v["features"], v["weights"], v["scale_um"],
                       v["depth_band"], v["chan_pct"], v["hp_um"]], sort_keys=True)


def evaluate_on(P, tiles):
    out = []
    for t in tiles:
        tile = NS._tiles.get(t["seg"])
        if tile is None:
            continue
        r = NS.eval_variant(P, tile)
        if r:
            out.append(r)
    return out


def main():
    t0 = time.time()
    print("FORENSICS on duty — attacking anything the swarm surfaces", flush=True)
    targets = NS.build_targets()
    by = {}
    for t in targets:
        by.setdefault(t["scroll"], []).append(t)
    scrolls = sorted(by)
    tune_s = scrolls[:max(1, len(scrolls)//3)]
    held_s = [s for s in scrolls if s not in tune_s]
    held_pool = [t for s in held_s for t in by[s]]

    rng = np.random.default_rng(90210)
    # forensics uses its OWN tiles — never the ones a worker scored on
    fresh = list(rng.choice(held_pool, size=min(18, len(held_pool)), replace=False))
    print(f"loading {len(fresh)} fresh tiles the swarm never used …", flush=True)
    for t in fresh:
        NS.load_tile(t)
    fresh = [t for t in fresh if NS._tiles.get(t["seg"])]
    print(f"  {len(fresh)} fresh tiles ready ({time.time()-t0:.0f}s)", flush=True)

    # negative controls: tiles whose ink coverage is tiny — mostly blank papyrus
    print("finding negative-control tiles (little or no ink) …", flush=True)
    negs = []
    for t in rng.permutation(held_pool)[:60]:
        tile = NS.load_tile(t)
        if tile is None:
            continue
        cov = float((tile["ink"] > 128).mean())
        if cov < 0.02:
            negs.append(t)
        if len(negs) >= 6:
            break
    print(f"  {len(negs)} negative-control tiles", flush=True)

    seen = load_seen()
    n_inv = 0
    while time.time() - t0 < HOURS*3600:
        cands = []
        for f in glob.glob(os.path.join(HERE, "swarm_w*.jsonl")):
            try:
                for line in open(f):
                    rec = json.loads(line)
                    if rec.get("heldout_median", 0) >= PICKUP_R and key_of(rec) not in seen:
                        cands.append(rec)
            except Exception:
                pass
        if not cands:
            time.sleep(20)
            continue
        cands.sort(key=lambda r: -r["heldout_median"])
        rec = cands[0]
        k = key_of(rec)
        seen.add(k); save_seen(seen)
        P = rec["variant"]
        n_inv += 1
        print(f"\n[{n_inv}] investigating r={rec['heldout_median']:+.3f} "
              f"{'+'.join(P['features'])}", flush=True)
        verdict = {"candidate": rec, "tests": {}, "t": round(time.time()-t0)}

        # --- 1 NEGATIVE CONTROL -------------------------------------------
        nres = evaluate_on(P, negs)
        if nres:
            nr = float(np.median([abs(x["r"]) for x in nres]))
            verdict["tests"]["negative_control"] = {"median_abs_r": nr, "n": len(nres),
                                                    "pass": nr < NEG_MAX}
            print(f"    negative control |r|={nr:.3f}  "
                  f"{'PASS' if nr < NEG_MAX else 'FAIL — fires on blank papyrus'}", flush=True)
            if nr >= NEG_MAX:
                json.dump(verdict, open(os.path.join(VERDICTS, f"v{n_inv:04d}_dead.json"), "w"), indent=1)
                continue
        else:
            verdict["tests"]["negative_control"] = {"pass": None, "note": "no controls"}

        # --- 2 FRESH HELD-OUT ---------------------------------------------
        fres = evaluate_on(P, fresh)
        if len(fres) < 8:
            print("    fresh draw: too few tiles", flush=True); continue
        rs = np.array([x["r"] for x in fres])
        sign = 1.0 if np.median(rs) > 0 else -1.0
        rs = sign*rs
        ps = np.array([x["p"] for x in fres])
        fm = float(np.median(rs)); ff = float((ps < 0.05).mean())
        verdict["tests"]["fresh_heldout"] = {"median_r": fm, "frac_signif": ff,
                                             "n": len(fres), "pass": fm >= FRESH_MIN}
        print(f"    fresh held-out r={fm:+.3f} ({ff*100:.0f}% signif, {len(fres)} tiles)  "
              f"{'PASS' if fm >= FRESH_MIN else 'FAIL — was the tile draw'}", flush=True)
        if fm < FRESH_MIN:
            json.dump(verdict, open(os.path.join(VERDICTS, f"v{n_inv:04d}_dead.json"), "w"), indent=1)
            continue

        # --- 3 PER-SCROLL --------------------------------------------------
        per = {}
        for x in fres:
            per.setdefault(x["scroll"], []).append(sign*x["r"])
        pm = {s: float(np.median(v)) for s, v in per.items()}
        worst = min(pm.values()) if pm else -1
        verdict["tests"]["per_scroll"] = {"medians": pm, "worst": worst,
                                          "pass": worst >= SCROLL_MIN and len(pm) >= 2}
        print(f"    per scroll: " + "  ".join(f"{s.replace('PHerc','')}={v:+.2f}"
              for s, v in sorted(pm.items())) +
              f"   {'PASS' if worst >= SCROLL_MIN and len(pm) >= 2 else 'FAIL — one scroll carrying it'}",
              flush=True)
        if not (worst >= SCROLL_MIN and len(pm) >= 2):
            json.dump(verdict, open(os.path.join(VERDICTS, f"v{n_inv:04d}_dead.json"), "w"), indent=1)
            continue

        # --- 4 STABILITY ----------------------------------------------------
        held = 0; tried = 0
        for _ in range(6):
            Q = json.loads(json.dumps(P))
            Q["scale_um"] = float(Q["scale_um"]) * float(rng.choice([0.8, 1.25]))
            Q["depth_band"] = int(max(3, Q["depth_band"] + rng.choice([-3, 3])))
            jr = evaluate_on(Q, fresh[:10])
            if len(jr) >= 6:
                tried += 1
                if sign*float(np.median([x["r"] for x in jr])) >= FRESH_MIN:
                    held += 1
        frac = held/max(tried, 1)
        verdict["tests"]["stability"] = {"held": held, "tried": tried, "frac": frac,
                                         "pass": frac >= STABLE_FRAC}
        print(f"    stability {held}/{tried} jittered neighbours hold  "
              f"{'PASS' if frac >= STABLE_FRAC else 'FAIL — sharp spike, i.e. noise'}", flush=True)
        if frac < STABLE_FRAC:
            json.dump(verdict, open(os.path.join(VERDICTS, f"v{n_inv:04d}_dead.json"), "w"), indent=1)
            continue

        # --- 5 EVIDENCE ------------------------------------------------------
        try:
            t = fresh[0]; tile = NS._tiles[t["seg"]]
            b = P["depth_band"]
            img = tile["vol"][max(0, tile["pk"]-b):tile["pk"]+b+1].mean(0)
            F = NS.make_features(img, tile["um"], P)
            f = NS.combine(F, P)
            def n8(a):
                lo, hi = np.percentile(a, 2), np.percentile(a, 98)
                return np.clip((a-lo)/max(hi-lo, 1e-6)*255, 0, 255).astype(np.uint8)
            S = 420
            sh = Image.new("L", (S*3+20, S), 0)
            sh.paste(Image.fromarray(n8(img)).resize((S, S), Image.LANCZOS), (0, 0))
            sh.paste(Image.fromarray(n8(f)).resize((S, S), Image.LANCZOS), (S+10, 0))
            sh.paste(Image.fromarray(np.clip(tile["ink"], 0, 255).astype(np.uint8)).resize((S, S), Image.LANCZOS), (2*S+20, 0))
            png = os.path.join(VERDICTS, f"v{n_inv:04d}_evidence.png")
            sh.save(png)
            verdict["evidence"] = png
        except Exception as e:
            verdict["evidence_error"] = str(e)

        verdict["SURVIVED"] = True
        json.dump(verdict, open(os.path.join(VERDICTS, f"v{n_inv:04d}_SURVIVED.json"), "w"), indent=1)
        with open(ALERT, "w") as f:
            f.write("# FORENSIC ALERT — a candidate survived every falsification test\n\n")
            f.write("```json\n"+json.dumps(verdict, indent=1)+"\n```\n\n")
            f.write("Survived: negative control, fresh held-out tiles, per-scroll\n"
                    "breakdown, and parameter jitter. Evidence image saved.\n\n"
                    "This is still NOT a reading. It means a texture measure tracks\n"
                    "published ink across scrolls it was never tuned on. Next: look at\n"
                    "the evidence image, then test on an unread scroll.\n")
        print("\n*** SURVIVED ALL TESTS — see FORENSIC_ALERT.md ***\n", flush=True)

    print(f"\nforensics done: {n_inv} investigations", flush=True)


if __name__ == "__main__":
    main()
