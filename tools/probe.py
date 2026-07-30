"""PROBE — rapid fire. Shoot through every depth and every quick transform,
see what pops.

WHY DEPTH IS THE AXIS NOBODY SWEPT

Every measurement in this project collapses depth before doing anything: mean
of a band around the sheet peak, then a texture statistic. Fourteen mechanisms,
all of them band-averaged.

But the ink is a SURFACE layer. If a signal is real it must peak at one depth
and fall away above and below it. A band mean smears that peak into its
neighbours, and worse, it hides the diagnostic: a real ink signal has a depth
PROFILE, a confound does not.

So this walks layer by layer through the sheet, runs a handful of cheap
transforms at each depth, and prints the profile. It is a screening tool, not
evidence — few tiles, few nulls, no ceremony. Anything that pops goes to
verify.py for the full battery.

THE FLAG CONDITION

  resolvable scrolls show a PEAK at some depth
  the blind scroll (ink never sampled) shows no peak at that depth

A confound has no reason to prefer a depth. Ink does — it was applied to a
surface. That asymmetry is the whole point of sweeping this axis.

Usage: python3 probe.py [n_tiles] [step]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

_argv, sys.argv = sys.argv, [sys.argv[0]]
import weave as WV
import scent as SC
sys.argv = _argv

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "findings")


# ---- the quick transforms. cheap on purpose. ------------------------------
def t_level(img, um):
    return img


def t_highpass(img, um):
    return img - P.box(img, max(2, int(round(700.0/um/2))))


def t_ridge(img, um):
    return WV_ridge(img, um)


def WV_ridge(img, um):
    return SC.ridge(img, um, 350.0)


def t_fringe(img, um):
    return SC.fringe(img, um, 40.0)


def t_fill(img, um):
    """weave_fill's core, computed on a single depth rather than a band."""
    corr = P.bandpass(img, um, 200.0, 600.0)
    ar = max(2, int(round(600.0/um)))
    amp = np.sqrt(np.maximum(P.box(corr*corr, ar), 0.0))
    nr = max(3, int(round(1500.0/um/2)))
    local = P.box(amp, nr)
    return (local - amp)/np.maximum(local, 1e-6)


def t_localsd(img, um):
    r = max(2, int(round(750.0/um/2)))
    mu = P.box(img, r)
    return np.sqrt(np.maximum(P.box(img*img, r) - mu*mu, 0.0))


TRANSFORMS = [("level", t_level), ("highpass", t_highpass), ("ridge", t_ridge),
              ("fringe", t_fringe), ("fill", t_fill), ("localsd", t_localsd)]


def quick_r(f, tile):
    """Correlation only — no null. Screening speed. Sign preserved."""
    fb, sub = P._align(f, tile)
    if fb is None or fb.std() < 1e-9:
        return None
    tg = (sub > 128).astype(np.float32)
    if tg.std() < 1e-9:
        return None
    r = float(np.corrcoef(fb.ravel(), tg.ravel())[0, 1])
    return r if np.isfinite(r) else None


def slab(tile, d, thick=3):
    """A thin slab at depth offset d from the sheet peak."""
    pk = tile["pk"]
    a = pk + d - thick//2
    v = P.layers(tile, a, a + thick)
    if v.shape[0] < 1:
        return None
    img = v.mean(0)
    return img if (img > 0).mean() >= 0.5 else None


def sweep(tiles, depths, label):
    """median r per (transform, depth), across tiles."""
    grid = np.full((len(TRANSFORMS), len(depths)), np.nan)
    for j, d in enumerate(depths):
        for i, (nm, fn) in enumerate(TRANSFORMS):
            rs = []
            for tile in tiles:
                img = slab(tile, d)
                if img is None:
                    continue
                try:
                    f = fn(img, tile["um"])
                except Exception:
                    continue
                r = quick_r(f, tile)
                if r is not None:
                    rs.append(r)
            if len(rs) >= 3:
                grid[i, j] = float(np.median(rs))
    return grid


def show(grid, depths, title):
    print(f"\n{title}")
    print("depth ->  " + " ".join(f"{d:+4d}" for d in depths))
    for i, (nm, _) in enumerate(TRANSFORMS):
        row = " ".join(("  . " if np.isnan(v) else f"{v:+4.2f}"[1:] if abs(v) < 1
                        else f"{v:+4.1f}") for v in grid[i])
        peak = np.nanmax(np.abs(grid[i])) if not np.all(np.isnan(grid[i])) else np.nan
        print(f"{nm:9s} " + row + f"   peak |r|={peak:.3f}" if np.isfinite(peak)
              else f"{nm:9s} " + row)


def main(n=6, step=3):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blindp = [t for s in bs for t in by[s]]

    def grab(pool, seed, k):
        rng = np.random.default_rng(seed)
        out = []
        for t in P.warm([pool[i] for i in rng.permutation(len(pool))[:k*3]], verbose=False):
            c = P.crop_coverage(t)
            if c is not None and 0.03 < c < 0.7:
                tl = P.load_tile(t)
                if tl is not None:
                    out.append(tl)
            if len(out) >= k:
                break
        return out

    t0 = time.time()
    tiles = grab(held, 11, n)
    blind = grab(blindp, 0, max(4, n//2))
    print(f"{len(tiles)} resolvable tiles, {len(blind)} blind tiles")
    if len(tiles) < 3:
        print("not enough tiles"); return

    depths = list(range(-18, 19, step))
    g = sweep(tiles, depths, "resolvable")
    show(g, depths, "RESOLVABLE HELD-OUT — median r vs published ink, by depth")
    gb = sweep(blind, depths, "blind")
    show(gb, depths, "BLIND PHerc0172 — same sweep. Ink was never sampled here.")

    print("\n" + "="*74)
    print("FLAGS — a peak on resolvable that the blind scroll does NOT share")
    print("="*74)
    flags = []
    for i, (nm, _) in enumerate(TRANSFORMS):
        row, brow = g[i], gb[i]
        if np.all(np.isnan(row)):
            continue
        j = int(np.nanargmax(np.abs(row)))
        pk_r = row[j]
        bl = np.nanmax(np.abs(brow)) if not np.all(np.isnan(brow)) else np.nan
        # is it a PEAK, or flat across depth? a real surface signal is peaked.
        finite = row[np.isfinite(row)]
        contrast = (abs(pk_r) - np.median(np.abs(finite))) if len(finite) > 3 else 0.0
        hit = abs(pk_r) >= 0.15 and (np.isnan(bl) or abs(bl) < 0.6*abs(pk_r)) and contrast >= 0.04
        flags.append(dict(transform=nm, best_depth=depths[j], r=float(pk_r),
                          blind_max=None if np.isnan(bl) else float(bl),
                          depth_contrast=float(contrast), flag=bool(hit)))
        print(f"  {nm:9s} peak r={pk_r:+.3f} at depth {depths[j]:+3d}   "
              f"blind max |r|={'--' if np.isnan(bl) else format(bl,'.3f')}   "
              f"depth contrast {contrast:+.3f}   {'*** FLAG ***' if hit else ''}")

    json.dump(dict(depths=depths, flags=flags), open(os.path.join(OUT, "probe.json"), "w"), indent=1)
    any_flag = any(f["flag"] for f in flags)
    print()
    if any_flag:
        print("Something popped. Next: rebuild it as a named feature and run\n"
              "verify.py on it. A screening hit is not a finding.")
    else:
        print("Nothing popped. Note the depth profiles above: if a transform is\n"
              "FLAT across depth it is not measuring a surface layer at all,\n"
              "which is itself the answer for that transform.")
    print(f"{time.time()-t0:.0f}s")
    return flags


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 6, int(a[1]) if len(a) > 1 else 3)
