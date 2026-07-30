"""SPATIAL NULL for the differential candidates.

Project standing rule: "Every correlation gets a spatial null (shift the
target, preserve autocorrelation). Pixel-permutation nulls are invalid here."

The differential's threshold is RELATIVE (top 4% of our map), so it selects
4% of pixels whether or not ink exists — in a margin window that could be
just the noisiest 4%. This asks the only question that matters: does the
candidate depend on our map being aligned with THIS papyrus, or would any
shifted version of our own map score the same?

A candidate that survives says: the hot structure sits where the published
map is cold FOR A REASON. A candidate whose rolled twins pass just as often
is a property of the marginal statistics and is hereby dead.

  python3 tools/null_differential.py
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D

N_ROLL = 24
RNG = np.random.default_rng(19)


def roll_nulls(ours, n=N_ROLL):
    """Large circular shifts (+ optional flips): identical histogram,
    identical autocorrelation, destroyed registration with the papyrus."""
    H, W = ours.shape
    out = []
    for _ in range(n):
        dy = int(RNG.integers(H // 8, H - H // 8))
        dx = int(RNG.integers(W // 8, W - W // 8))
        r = np.roll(np.roll(ours, dy, 0), dx, 1)
        k = int(RNG.integers(0, 4))
        if k == 1:
            r = r[::-1].copy()
        elif k == 2:
            r = r[:, ::-1].copy()
        elif k == 3:
            r = r[::-1, ::-1].copy()
        out.append(r)
    return out


def main():
    dj = json.load(open(os.path.join(D.LB, "differential.json")))
    cands = dj["candidates"]
    if not cands:
        print("no candidates to test")
        return
    print(f"spatial null: {N_ROLL} rolls per candidate "
          f"(same histogram, same autocorrelation, no registration)\n")
    print(f"{'segment':28} {'real':>5} {'nulls pass':>11} {'p':>7}  verdict")
    rows = []
    for c in cands:
        ours = np.load(os.path.join(D.LB, f"map_{c['tag']}.npy"))
        meta = json.load(open(os.path.join(D.LB, f"meta_{c['tag']}.json")))
        pub = D.pub_crop(meta)
        _, real_comps, real_r, _ = D.gate(ours, pub)
        n_real = len(real_comps)

        passes, counts = 0, []
        for r in roll_nulls(ours):
            _, rc, _, _ = D.gate(r, pub)
            counts.append(len(rc))
            if 2 <= len(rc) <= 9:
                passes += 1
        # one-sided p: how often a null matches or beats the real count
        beat = sum(1 for k in counts if k >= n_real)
        p = (beat + 1) / (len(counts) + 1)
        verdict = ("SURVIVES" if p < 0.05 and passes < len(counts) * 0.5
                   else "DEAD — null does this too")
        print(f"{c['seg'][:28]:28} {n_real:5d} {passes:5d}/{len(counts):<5} "
              f"{p:7.3f}  {verdict}")
        rows.append(dict(seg=c["seg"], tag=c["tag"], n_real=n_real,
                         null_pass=passes, null_n=len(counts),
                         null_mean_comps=round(float(np.mean(counts)), 2),
                         p=round(p, 4), survives=bool(p < 0.05 and
                                                      passes < len(counts)*0.5)))
    json.dump(rows, open(os.path.join(D.LB, "null_test.json"), "w"), indent=1)
    live = [r for r in rows if r["survives"]]
    print(f"\n{len(live)}/{len(rows)} candidates survive the spatial null")
    if not live:
        print("VERDICT: the differential's margin candidates are a property of\n"
              "the top-4% relative threshold, not of the papyrus. Publishable\n"
              "negative; the gate needs an ABSOLUTE confidence floor.")


if __name__ == "__main__":
    main()
