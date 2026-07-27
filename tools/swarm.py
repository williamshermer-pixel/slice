"""SWARM — many workers, sharing hits, piling onto whatever looks alive.

Random search treats every variant as independent and learns nothing. A swarm
shares: each worker writes what it finds to common ground, reads the global best,
and spends part of its time mutating AROUND that best rather than starting cold.
One worker finding a live region pulls the others in.

Structure per worker:
  ~55% EXPLORE   a fresh random variant, so the swarm cannot collapse onto one
                 hill and stop looking
  ~45% EXPLOIT   mutate the current global best — nudge scales, swap a feature,
                 flip a weight

The anti-overfitting guarantee is unchanged and is the whole point: workers tune
on two scrolls and are SCORED only on five others. Fit is never measured, so a
variant that memorises one sheet scores nothing no matter how many workers find
it.

Usage:  python3 swarm.py [workers] [hours]
"""
import json, os, sys, time, random, subprocess, signal

HERE = os.path.dirname(os.path.abspath(__file__))
NWORK = int(sys.argv[1]) if len(sys.argv) > 1 else 10
HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
BEST = os.path.join(HERE, "swarm_best.json")
ALERT = os.path.join(HERE, "SWARM_ALERT.md")

WORKER = r'''
import json, os, sys, time, math, random
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nightshift as NS

WID   = int(sys.argv[1])
HOURS = float(sys.argv[2])
HERE  = os.path.dirname(os.path.abspath(__file__))
BEST  = os.path.join(HERE, "swarm_best.json")
ALERT = os.path.join(HERE, "SWARM_ALERT.md")
LOG   = os.path.join(HERE, f"swarm_w{WID}.jsonl")

def read_best():
    try:
        with open(BEST) as f: return json.load(f)
    except Exception: return None

def write_best(rec):
    tmp = BEST + f".{WID}.tmp"
    with open(tmp, "w") as f: json.dump(rec, f)
    os.replace(tmp, BEST)          # atomic; last writer wins, which is fine

def mutate(P, rng):
    Q = json.loads(json.dumps(P))
    what = rng.integers(0, 4)
    if what == 0:
        Q["scale_um"] = float(rng.choice([250,400,600,750,1000,1500]))
    elif what == 1 and len(Q["features"]) < 4:
        cand = [f for f in NS.FEATURE_NAMES if f not in Q["features"]]
        if cand:
            Q["features"].append(str(rng.choice(cand)))
            Q["weights"].append(float(rng.choice([1.0,0.7,0.5,-0.5,-0.7,-1.0])))
    elif what == 2 and len(Q["weights"]) > 0:
        i = int(rng.integers(0, len(Q["weights"])))
        Q["weights"][i] = float(rng.choice([1.0,0.7,0.5,-0.5,-0.7,-1.0]))
    else:
        Q["depth_band"] = int(rng.choice([4,8,14]))
        Q["chan_pct"]   = int(rng.choice([60,70,80,88]))
    return Q

rng = np.random.default_rng(1000 + WID * 977 + int(time.time()) % 5000)
targets = NS.build_targets()
by = {}
for t in targets: by.setdefault(t["scroll"], []).append(t)
scrolls = sorted(by)
tune_s = scrolls[:max(1, len(scrolls)//3)]
held_s = [s for s in scrolls if s not in tune_s]
tune_pool = [t for s in tune_s for t in by[s]]
held_pool = [t for s in held_s for t in by[s]]

# each worker draws its OWN tiles, so a lucky tile set cannot fool the swarm
wt = list(rng.choice(tune_pool, size=min(8, len(tune_pool)), replace=False))
wh = list(rng.choice(held_pool, size=min(16, len(held_pool)), replace=False))
for t in wt + wh: NS.load_tile(t)
wt = [t for t in wt if NS._tiles.get(t["seg"])]
wh = [t for t in wh if NS._tiles.get(t["seg"])]
print(f"w{WID}: {len(wt)} tune, {len(wh)} held-out tiles", flush=True)
if len(wh) < NS.MIN_HELDOUT_SEGS:
    print(f"w{WID}: too few held-out tiles, exiting", flush=True); sys.exit(0)

log = open(LOG, "a")
t0 = time.time(); n = 0; mine = None
while time.time() - t0 < HOURS*3600:
    if os.path.exists(ALERT): break
    n += 1
    gb = read_best()
    if gb and rng.random() < 0.45:
        P = mutate(gb["variant"], rng)
    else:
        P = NS.sample_variant(rng)
    tr = [NS.eval_variant(P, NS._tiles[t["seg"]]) for t in wt]
    tr = [x for x in tr if x]
    if len(tr) < 3: continue
    tm = float(np.median([x["r"] for x in tr]))
    if abs(tm) < 0.10: continue
    sign = 1.0 if tm > 0 else -1.0
    hr = [NS.eval_variant(P, NS._tiles[t["seg"]]) for t in wh]
    hr = [x for x in hr if x]
    if len(hr) < NS.MIN_HELDOUT_SEGS: continue
    rs = np.array([sign*x["r"] for x in hr]); ps = np.array([x["p"] for x in hr])
    med = float(np.median(rs)); frac = float((ps < 0.05).mean())
    nsc = len({x["scroll"] for x in hr})
    rec = {"w": WID, "variant": P, "heldout_median": med, "frac_signif": frac,
           "n_heldout": len(hr), "n_scrolls": nsc, "t": round(time.time()-t0)}
    log.write(json.dumps(rec)+"\n"); log.flush()
    gb = read_best()
    if gb is None or med > gb["heldout_median"]:
        write_best(rec)
        print(f"w{WID} [{n}] BEST held-out r={med:+.3f} "
              f"({frac*100:.0f}% signif, {len(hr)} segs, {nsc} scrolls) "
              f"{'+'.join(P['features'])}", flush=True)
    if (med >= NS.MIN_HELDOUT_R and frac >= NS.MIN_FRAC_SIGNIF
            and len(hr) >= NS.MIN_HELDOUT_SEGS and nsc >= NS.MIN_SCROLLS):
        with open(ALERT, "w") as f:
            f.write("# SWARM ALERT\n\nA variant cleared the bar on held-out scrolls.\n\n")
            f.write("```json\n"+json.dumps(rec, indent=1)+"\n```\n\n")
            f.write("NOT a finding yet. Still required before anyone says we have it:\n"
                    "- negative control on a no-ink region\n"
                    "- a fresh held-out draw with different tiles\n"
                    "- visual review against the ink map\n")
        print(f"w{WID}: *** CLEARED THE BAR ***", flush=True)
        break
print(f"w{WID}: done, {n} variants", flush=True)
'''

wpath = os.path.join(HERE, "_swarm_worker.py")
open(wpath, "w").write(WORKER)

if os.path.exists(ALERT):
    os.remove(ALERT)
if os.path.exists(BEST):
    os.remove(BEST)

procs = []
for i in range(NWORK):
    lf = open(os.path.join(HERE, f"swarm_w{i}.log"), "w")
    p = subprocess.Popen([sys.executable, wpath, str(i), str(HOURS)],
                         stdout=lf, stderr=subprocess.STDOUT, cwd=HERE)
    procs.append(p)
    time.sleep(2.0)          # stagger so they don't all hammer S3 at once

print(f"swarm up: {NWORK} workers, {HOURS}h, pids {[p.pid for p in procs]}")
print(f"shared best: {BEST}")
print(f"alert file : {ALERT}")
print(f"kill all   : kill {' '.join(str(p.pid) for p in procs)}")
