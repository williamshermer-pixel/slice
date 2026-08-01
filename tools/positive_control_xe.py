#!/usr/bin/env python3
"""Synthetic positive control for the cross-energy pipeline.

This is the check whose absence let every other bug ship on 2026-07-31: a warp
applied with the wrong sign, a Jaccard null that did not preserve call density,
a conjunction null that dropped called-text z-values into the search window,
and a line-test null that was the identity operation. Every one of those would
have been caught in three minutes by planting known ink and asking whether the
instrument finds it.

Rule from here: no detector in this project ships without a positive control
that fails when the detector is broken.

Three tests, each with a KNOWN answer:

  1 warp        plant a known shift in B, check the registration recovers it
                and that warping IMPROVES correlation rather than degrading it
  2 recovery    plant letters of rising amplitude in both maps, inside the
                search region, and require the conjunction to find them with
                rising significance
  3 null sanity plant NOTHING and require the null distribution to be a real
                distribution: not degenerate, not identical to the observation,
                and centred below the observed statistic only by chance

    python3 tools/positive_control_xe.py [segment]
"""
import glob, os, sys
import numpy as np
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
DS8_UM = 18.064
FAILS = []


def ok(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)
    return cond


def main():
    import importlib
    ce = importlib.import_module("crossenergy_1667")
    cj = importlib.import_module("conjunction_1667")

    d = os.path.join(ROOT, "out", "xe_PHerc0139")
    seg = sys.argv[1] if len(sys.argv) > 1 else "20250108000003"
    z = np.load(os.path.join(d, f"xe_{seg}.npz"))
    A = z["A"].astype(np.float32)
    m = z["m"]
    LET = 1.61 * 1000 / DS8_UM

    # ---- 1. warp recovers a known shift, and helps ----------------------
    print("1. registration")
    TRUE = (11, -7)
    B = np.roll(A, TRUE, (0, 1))
    hp = lambda x: x - ndimage.gaussian_filter(np.where(m, x, 0.0), LET)
    fy, fx, okb = ce.block_field(hp(A), hp(B), m)
    got = (float(np.median(fy[okb])) if okb.any() else 0.0,
           float(np.median(fx[okb])) if okb.any() else 0.0)
    Bw = ce.warp(B, fy, fx)
    r_raw = float(np.corrcoef(hp(A)[m], hp(B)[m])[0, 1])
    r_warp = float(np.corrcoef(hp(A)[m], hp(Bw)[m])[0, 1])
    # The field stores k = -s by construction (phase correlation peaks at -s),
    # and warp() samples at y - FY. So the CORRECT field is the negative of the
    # planted shift; asserting equality was the test being wrong, not the code.
    ok("1a field recovers the planted shift (as -s, the stored convention)",
       abs(got[0] + TRUE[0]) <= 2 and abs(got[1] + TRUE[1]) <= 2,
       f"planted {TRUE}, field ({got[0]:.0f}, {got[1]:.0f}), expected negated")
    ok("1b warping IMPROVES correlation", r_warp > r_raw + 0.2,
       f"raw {r_raw:.3f} -> warped {r_warp:.3f}")

    # ---- 2. conjunction recovers planted ink ----------------------------
    print("\n2. conjunction recovers planted ink")
    B0 = z["B"].astype(np.float32)
    ca, cb = z["ca"], z["cb"]
    called = ndimage.uniform_filter((ca | cb).astype(np.float32),
                                    2 * cj.KEEPOUT_PX + 1) > 1e-6
    search = m & ~called & (ndimage.distance_transform_edt(m) >= 3.0 * LET)
    if search.sum() < 20000:
        print("  (search region too small on this segment)")
    clear = ndimage.distance_transform_edt(search)
    sites = np.argwhere(clear >= 0.9 * LET)
    ok("2a a plantable site exists", len(sites) > 0, f"{len(sites)} sites")
    if len(sites):
        rng = np.random.default_rng(5)
        y, x = sites[rng.integers(0, len(sites))]
        sig = LET / 2.355
        h = int(1.5 * LET)
        yy = np.arange(-h, h + 1)
        g = np.exp(-(yy ** 2) / (2 * sig ** 2))
        stamp = np.outer(g, g).astype(np.float32)
        hpA = A - ndimage.gaussian_filter(np.where(m, A, 0.0), LET)
        unit = float(np.median(cj.letter_box(hpA, m)[ca & m]))
        prev = None
        rows = []
        for alpha in (0.0, 0.5, 1.0, 2.0):
            Ai, Bi = A.copy(), B0.copy()
            sl = (slice(y - h, y + h + 1), slice(x - h, x + h + 1))
            Ai[sl] += alpha * unit * stamp
            Bi[sl] += alpha * unit * stamp
            za = cj.zmap(Ai, m, search)
            zb = cj.zmap(Bi, m, search)
            J = np.minimum(za, zb)
            rows.append((alpha, float(J[y, x])))
        for a, v in rows:
            print(f"      alpha {a:>4}  J at planted site {v:6.2f}")
        mono = all(rows[i][1] < rows[i + 1][1] for i in range(len(rows) - 1))
        ok("2b response rises monotonically with planted amplitude", mono)
        # Judge against the null, not an arbitrary constant.
        zaq = cj.zmap(A, m, search); zbq = cj.zmap(B0, m, search)
        rng2 = np.random.default_rng(3)
        nd, tries = [], 0
        # tries guard: without it, a run of failed draws (overlap floor) spins
        # forever at 100% CPU. Every retry loop in this project gets a ceiling.
        while len(nd) < 20 and tries < 200:
            tries += 1
            sy = int(rng2.integers(int(3*LET), max(int(3*LET)+1, int(0.35*m.shape[0]))))
            sx = int(rng2.integers(int(3*LET), max(int(3*LET)+1, int(0.35*m.shape[1]))))
            v = cj.null_statistic(zaq, zbq, search, (sy, sx), LET)
            if v is not None:
                nd.append(v[1])          # null_s half of the matched pair
        thr = float(np.percentile(nd, 95)) if nd else 3.0
        ok("2c planted ink at real amplitude clears the null",
           rows[2][1] > thr, f"J={rows[2][1]:.2f} vs null p95 {thr:.2f}")

    # ---- 3. the null must be a real distribution ------------------------
    print("\n3. null sanity (no planted ink)")
    za = cj.zmap(A, m, search)
    zb = cj.zmap(B0, m, search)
    obs = cj.peaks(np.minimum(za, zb), search, 1, int(2 * LET))
    obs = obs[0][0] if obs else float("nan")
    rng = np.random.default_rng(9)
    lo = int(3 * LET)
    hy = max(lo + 1, int(0.35 * m.shape[0]))
    hx = max(lo + 1, int(0.35 * m.shape[1]))
    pairs_, tries = [], 0
    while len(pairs_) < 24 and tries < 24 * 12:
        tries += 1
        sy = int(rng.integers(lo, hy)) * (1 if rng.random() < 0.5 else -1)
        sx = int(rng.integers(lo, hx)) * (1 if rng.random() < 0.5 else -1)
        v = cj.null_statistic(za, zb, search, (sy, sx), LET)
        if v is not None:
            pairs_.append(v)
    obs_s = np.array([a for a, b in pairs_])
    nulls = np.array([b for a, b in pairs_])
    ok("3a null produced enough matched pairs", nulls.size >= 12,
       f"{nulls.size}/24 in {tries} tries")
    if nulls.size:
        ok("3b null is not the identity of its matched observation",
           not np.allclose(nulls, obs_s, atol=1e-6),
           f"matched-obs mean {obs_s.mean():.3f}, null mean {nulls.mean():.3f}")
        ok("3c null has spread", float(nulls.std()) > 1e-3,
           f"sd {nulls.std():.3f}")
        ok("3d null does not systematically beat its matched observation",
           float(np.mean(nulls > obs_s)) < 0.9,
           f"{100*np.mean(nulls>obs_s):.0f}% of pairs null-dominant")

    print(f"\n{'='*58}")
    print("POSITIVE CONTROL FAILED: " + ", ".join(FAILS) if FAILS
          else "positive control passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
