"""DEPTH HUNT — does looking ACROSS depth see ink the fixed band missed?

The depth profiles make a clean experiment possible. Offset 27 is exactly the
z27..z89 band every map in this project used, so within one window:

    prof[k=27]     = the old fixed-band map
    prof.max(0)    = the best response at ANY depth

Same papyrus, same model, same window — the only difference is whether depth
was searched. Part 1 asks whether that helps at all, scored against the
published calls on known text. Part 2 hunts only if it does, and every
candidate still faces the spatial null that killed eleven before it.

  python3 tools/depth_hunt.py
"""
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SCROLL", "PHerc0139")
import differential_0139 as D
from letterscale_0139 import boxmean, BOX

ROOT = D.ROOT
PROF = os.path.join(ROOT, "out", "lostbook_prof")
N_ROLL = 24
RNG = np.random.default_rng(31)


def auc(score, pos, neg):
    a, b = score[pos], score[neg]
    if a.size < 200 or b.size < 200:
        return float("nan")
    s = np.concatenate([a, b])
    y = np.concatenate([np.ones(a.size, bool), np.zeros(b.size, bool)])
    o = np.argsort(s)
    rk = np.empty(s.size); rk[o] = np.arange(1, s.size + 1)
    v = (rk[y].sum() - a.size * (a.size + 1) / 2) / (a.size * b.size)
    return float(max(v, 1 - v))


def main():
    rows = []
    print("PART 1 — does depth search improve agreement with published calls?\n")
    print(f"{'window':30} {'fixed z27':>10} {'depth-max':>10} {'delta':>8}")
    for pf in sorted(glob.glob(os.path.join(PROF, "prof_*.npy"))):
        tag = os.path.basename(pf)[5:-4]
        mfp = os.path.join(PROF, f"meta_{tag}.json")
        if not os.path.exists(mfp):
            continue
        meta = json.load(open(mfp))
        if 27 not in meta["offsets"]:
            continue
        k27 = meta["offsets"].index(27)
        prof = np.load(pf)
        try:
            pub = D.pub_crop(meta)
        except Exception:
            continue
        ink, blank = pub > 128, pub < 60
        if ink.sum() < 3000 or blank.sum() < 3000:
            continue
        a_fixed = auc(prof[k27], ink, blank)
        a_depth = auc(prof.max(0), ink, blank)
        if np.isnan(a_fixed) or np.isnan(a_depth):
            continue
        rows.append((tag, meta, a_fixed, a_depth))
        print(f"{meta['seg'].split('/')[-2][:28]:30} {a_fixed:10.3f} "
              f"{a_depth:10.3f} {a_depth-a_fixed:+8.3f}")

    if not rows:
        sys.exit("no comparable windows yet")
    d = np.array([r[3] - r[2] for r in rows])
    print(f"\n  {len(rows)} windows · mean delta {d.mean():+.4f} · "
          f"improved in {int((d > 0).sum())}/{len(d)}")
    # paired sign test
    k = int((d > 0).sum())
    n = len(d)
    from math import comb
    p = sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n
    print(f"  sign test p = {p:.4f}")
    verdict_help = d.mean() > 0.002 and p < 0.05
    print("  VERDICT:", "depth search HELPS — hunt with it" if verdict_help
          else "no reliable gain; the fixed band already caught what the model sees")

    print("\nPART 2 — hunt with the depth-max map (ours-hot, published-cold)\n")
    floor = json.load(open(os.path.join(D.LB, "floor.json")))["floor"]
    clear = int(1.5 * D.MM)
    hits = []
    for tag, meta, a_fixed, a_depth in rows:
        prof = np.load(os.path.join(PROF, f"prof_{tag}.npy"))
        pub = D.pub_crop(meta)
        peak = prof.max(0)
        called = (pub > 128).astype(np.float32)
        c = np.pad(called, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        kk = min(clear, 1023)
        s = c[kk:, kk:] - c[:-kk, kk:] - c[kk:, :-kk] + c[:-kk, :-kk]
        far = np.zeros((1024, 1024), bool)
        far[:s.shape[0], :s.shape[1]] = s <= 0
        legal = far & (pub < 60)
        if legal.mean() < 0.01:
            continue
        bm = boxmean(peak, BOX)
        lg = legal[:bm.shape[0], :bm.shape[1]]
        nullv = bm[lg]
        if nullv.size < 500:
            continue
        thr = float(np.percentile(nullv, 99.9))
        hot = lg & (bm > thr)
        comps = [cc for cc in D.components(hot) if cc["area"] >= 20]
        if len(comps) >= 1:
            hits.append((tag, meta, len(comps), float(bm[hot].max()), thr, lg))
            print(f"  {meta['seg'].split('/')[-2][:26]:28} "
                  f"{len(comps)} cluster(s) peak {bm[hot].max():.3f}  <-- CANDIDATE")
    if not hits:
        print("  no candidates — depth-searched maps are quiet where the "
              "published maps are cold")
        return
    print("\n  spatial null on each:")
    live = 0
    for tag, meta, n_c, pk, thr, lg in hits:
        prof = np.load(os.path.join(PROF, f"prof_{tag}.npy"))
        peak = prof.max(0)
        beat = 0
        for _ in range(N_ROLL):
            dy = int(RNG.integers(128, 896)); dx = int(RNG.integers(128, 896))
            rl = np.roll(np.roll(peak, dy, 0), dx, 1)
            b2 = boxmean(rl, BOX)
            h2 = lg & (b2 > thr)
            c2 = [cc for cc in D.components(h2) if cc["area"] >= 20]
            if len(c2) >= n_c:
                beat += 1
        pv = (beat + 1) / (N_ROLL + 1)
        ok = pv < 0.05
        live += ok
        print(f"    {meta['seg'].split('/')[-2][:26]:28} n={n_c} "
              f"nulls>=n {beat}/{N_ROLL} p={pv:.3f} "
              f"{'SURVIVES' if ok else 'dead'}")
    print(f"\n  {live} survive the spatial null")


if __name__ == "__main__":
    main()
