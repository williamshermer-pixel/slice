"""LEAD SWEEP — depth-resolved attenuation contrast, the reconciliation test.

The question (science-deep-dive.md Part II-B): the community read PHerc. 172's
title and hypothesises its ink is unusually attenuating (lead-like). Our blind
-scroll control assumed the opposite. Our earlier lead test measured a band
around the interior peak — and we later learned the analysis window never
reaches the sheet faces (data-capabilities.md), so the layer could have been
missed entirely.

This test cannot miss it: it sweeps EVERY depth layer of the full uncropped
stack and asks, per layer, whether ink-labelled pixels are brighter than
bare-labelled pixels, in SD units, against a spatial null that rolls the
label map and preserves its autocorrelation.

Labels are the published ink maps, split scale-free by percentile (top 20% =
ink, bottom 20% = bare) — absolute thresholds are exposure-dependent and, on
PHerc0172, the published model emits mid-range values nearly everywhere.

Read the output as:
  - excursion beyond the null envelope at SOME depth on PHerc0172
        -> the 7.91 um data DOES carry attenuation contrast aligned with the
           published maps; the blind-scroll control is compromised; the lead
           hypothesis is live on public data.
  - flat everywhere on PHerc0172, excursion present on the comparator
        -> no lead-driven contrast in the public 172 surface volumes; the
           physics control stands for this data product; the community's
           hypothesis, if true, lives only in scans we do not have.
  - flat on the blank controls, always (sanity: percentile-splitting a
        no-ink map must produce nothing).

Usage: python3 lead_sweep.py [n_tiles_per_group]
Writes findings/lead_sweep.json and prints the verdict table.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "findings", "lead_sweep.json")

HP_UM = 350.0          # high-pass at stroke/letter scale
N_NULLS = 24
PCT = 20               # label percentile split


def full_stack(t):
    """Full uncropped stack + alignment fields, straight from the disk cache
    (load_tile crops in memory; the cache keeps everything)."""
    p = P._cache_path(t["seg"])
    if not os.path.exists(p):
        if P.load_tile(t) is None:          # warms the cache
            return None
    try:
        d = np.load(p, allow_pickle=False)
        if d["vol"].size == 0:
            return None
        return dict(vol=d["vol"], pk=int(d["pk"]), ink=d["ink"].astype(np.float32),
                    ds=float(d["ds"]), iy=int(d["iy"]), ix=int(d["ix"]),
                    um=float(P.true_um(t) or d["um"]), scroll=t["scroll"],
                    seg=t["seg"])
    except Exception:
        return None


def sweep_tile(t, rng):
    tile = full_stack(t)
    if tile is None:
        return None
    vol, um = tile["vol"], tile["um"]
    D = vol.shape[0]
    r_hp = max(2, int(round(HP_UM / um / 2)))

    # Bin the FIRST layer to discover the aligned grid once; build masks there.
    probe, sub = P._align(vol[0].astype(np.float32), tile)
    if probe is None or sub.std() < 1e-9:
        return None
    lo, hi = np.percentile(sub, [PCT, 100 - PCT])
    if not (hi > lo):
        return None
    ink_m, bare_m = sub >= hi, sub <= lo
    if ink_m.sum() < 40 or bare_m.sum() < 40:
        return None

    # Pre-build null masks: same label map, rolled. Autocorrelation preserved.
    n0, n1 = sub.shape
    rolls = [(int(rng.integers(6, n0 - 6)), int(rng.integers(6, n1 - 6)))
             for _ in range(N_NULLS)]
    null_masks = []
    for dy, dx in rolls:
        s = np.roll(np.roll(sub, dy, 0), dx, 1)
        null_masks.append((s >= hi, s <= lo))

    curves = {"raw": np.zeros(D), "hp": np.zeros(D)}
    nulls = {"raw": np.zeros((N_NULLS, D)), "hp": np.zeros((N_NULLS, D))}
    for d in range(D):
        lay = vol[d].astype(np.float32)
        hp = lay - P.box(lay, r_hp)
        for key, img in (("raw", lay), ("hp", hp)):
            fb, _ = P._align(img, tile)
            sd = fb.std()
            if sd < 1e-9:
                continue
            curves[key][d] = (fb[ink_m].mean() - fb[bare_m].mean()) / sd
            for k, (im, bm) in enumerate(null_masks):
                nulls[key][k, d] = (fb[im].mean() - fb[bm].mean()) / sd

    return dict(seg=tile["seg"], scroll=tile["scroll"], um=um, D=D,
                pk=tile["pk"],
                curves={k: v.tolist() for k, v in curves.items()},
                null_lo={k: np.percentile(v, 2.5, axis=0).tolist()
                         for k, v in nulls.items()},
                null_hi={k: np.percentile(v, 97.5, axis=0).tolist()
                         for k, v in nulls.items()})


def group_verdict(results, key="hp"):
    """Median curve across tiles, aligned on the sheet peak, and the maximum
    excursion beyond the pooled null envelope."""
    if not results:
        return None
    # common depth axis: um relative to peak
    axes, vals, nl, nh = [], [], [], []
    for r in results:
        ax = (np.arange(r["D"]) - r["pk"]) * r["um"]
        axes.append(ax)
        vals.append(np.array(r["curves"][key]))
        nl.append(np.array(r["null_lo"][key]))
        nh.append(np.array(r["null_hi"][key]))
    lo = max(a.min() for a in axes)
    hi = min(a.max() for a in axes)
    if hi <= lo:
        return None
    grid = np.arange(lo, hi, min(r["um"] for r in results))
    V = np.median([np.interp(grid, a, v) for a, v in zip(axes, vals)], axis=0)
    L = np.median([np.interp(grid, a, v) for a, v in zip(axes, nl)], axis=0)
    H = np.median([np.interp(grid, a, v) for a, v in zip(axes, nh)], axis=0)
    exc = np.where(V > H, V - H, np.where(V < L, V - L, 0.0))
    i = int(np.abs(exc).argmax())
    return dict(n=len(results), grid_um=[float(grid[0]), float(grid[-1])],
                max_excursion=float(exc[i]), at_um=float(grid[i]),
                curve_max=float(V.max()), curve_min=float(V.min()),
                envelope=[float(L[i]), float(H[i])], value_there=float(V[i]))


def main(n_per=10):
    rng = np.random.default_rng(20260728)
    tg = P.targets()
    by = {}
    for t in tg:
        by.setdefault(t["scroll"], []).append(t)

    groups = {
        "PHerc0172_blind": by.get("PHerc0172", [])[:n_per],
        "PHerc0500P2_comparator": by.get("PHerc0500P2", [])[:n_per],
        "PHerc0139_comparator": by.get("PHerc0139", [])[:n_per],
    }
    # verified-blank sanity: crops with essentially no ink
    negs = P.find_negatives([t for s in ("PHerc0343P", "PHerc0500P2")
                             for t in by.get(s, [])], n=6)
    groups["verified_blank_sanity"] = negs

    out = {}
    for name, tiles in groups.items():
        res = []
        for t in tiles:
            r = sweep_tile(t, rng)
            if r is not None:
                res.append(r)
            if len(res) >= n_per:
                break
        v_raw = group_verdict(res, "raw")
        v_hp = group_verdict(res, "hp")
        out[name] = dict(tiles=[r["seg"].split("/")[-3] if "/" in r["seg"]
                                else r["seg"] for r in res],
                         raw=v_raw, hp=v_hp)
        print(f"\n== {name} ({len(res)} tiles) ==", flush=True)
        for k, v in (("raw", v_raw), ("hp", v_hp)):
            if v is None:
                print(f"  {k}: insufficient tiles")
                continue
            print(f"  {k}: max excursion beyond null {v['max_excursion']:+.3f} sd "
                  f"at {v['at_um']:+.0f} um from peak "
                  f"(curve {v['curve_min']:+.3f}..{v['curve_max']:+.3f}, "
                  f"envelope there [{v['envelope'][0]:+.3f},{v['envelope'][1]:+.3f}])",
                  flush=True)

    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
