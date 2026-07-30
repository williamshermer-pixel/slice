"""WEAVE — measure the ink RELATIVE TO the fibre lattice, not against it.

THE IDEA

Papyrus is laminated strips laid at right angles, so a sheet face is a
quasi-periodic corrugation: fibre crests with gaps between them. The ink is
brushed on top and, per Mocella et al., "does not completely penetrate the
fibres". Two physical consequences follow, and they are the two things to look
for:

  LIFT     ink sitting on a crest raises it slightly
  FILL     ink wicking into the gap between fibres makes the trough shallower

Both are statements about the ink RELATIVE TO the local fibre geometry. Every
previous measure in this project was fibre-agnostic — isotropic box filters,
gradients, structure tensors — which is why they all end up measuring the weave
itself, the loudest thing on the sheet.

WHY FILTERING THE WEAVE OUT CANNOT WORK

Mechanism 4 in this project was a frequency notch, and it died with the finding
that weave and stroke occupy the same band: 335 um against 346 um. They are the
same scale. No filter separates them, and every attempt to notch the weave
notches the letters too.

But they differ in STRUCTURE, not scale. The weave is periodic and locally
oriented; a letter stroke is not. So rather than removing the weave, model it —
locally estimate its orientation and period, demodulate against it, and measure
the corrugation AMPLITUDE. Where ink has filled the gaps, the corrugation is
shallower. That is a phase-and-geometry argument, and it is available precisely
because the notch approach failed.

WHAT IT COMPUTES

  weave_amp     local peak-to-trough corrugation amplitude of the fibre lattice
  weave_fill    NEGATIVE amplitude anomaly — corrugation shallower than its
                own neighbourhood predicts, i.e. gaps filled
  weave_lift    positive residual ON the crests only — ink riding on fibre tops
  weave_resid   energy that does not fit the local oriented periodic model
  weave_period  the fibre period itself, as a control: if a candidate tracks
                THIS, it is reading the weave, not the ink

That last one is deliberately a trap. Any combination that leans on
`weave_period` is measuring papyrus structure and should be scored down.

Usage: python3 weave.py [n_tiles]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "findings")

DEFAULT = dict(
    band=8,
    fibre_lo_um=200.0,     # fibre corrugation lives around 335 um
    fibre_hi_um=600.0,
    neigh_um=1500.0,       # neighbourhood the anomaly is measured against
    crest_pct=65.0,        # percentile defining "on a crest"
    offset=0,              # depth offset from the sheet peak
)


def _orient(img, um, scale_um):
    """Local dominant orientation and coherence from the structure tensor."""
    r = max(2, int(round(scale_um/um/2)))
    gy, gx = np.gradient(img)
    Jxx, Jyy, Jxy = P.box(gx*gx, r), P.box(gy*gy, r), P.box(gx*gy, r)
    coh = np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2)/np.maximum(Jxx+Jyy, 1e-6)
    ang = 0.5*np.arctan2(2*Jxy, Jxx-Jyy)
    return ang, coh


def weave_features(tile, p=None):
    p = dict(DEFAULT, **(p or {}))
    um = tile["um"]
    img = P.mid_image(tile, int(p["band"]), int(p.get("offset", 0)))
    if (img > 0).mean() < 0.5:
        return {}

    # isolate the fibre corrugation band
    corr = P.bandpass(img, um, p["fibre_lo_um"], p["fibre_hi_um"])

    # local corrugation AMPLITUDE — the depth of the weave relief.
    # RMS in a window of a few fibre periods.
    ar = max(2, int(round(p["fibre_hi_um"]/um)))
    amp = np.sqrt(np.maximum(P.box(corr*corr, ar), 0.0))

    # anomaly: shallower than the surrounding sheet predicts.
    # normalised, so it does not simply restate "this area is low contrast".
    nr = max(3, int(round(p["neigh_um"]/um/2)))
    local = P.box(amp, nr)
    fill = (local - amp)/np.maximum(local, 1e-6)

    # LIFT: positive residual restricted to crests. A crest is where the
    # corrugation is already high, so ink there shows as extra height on top
    # of an existing ridge rather than as a new ridge.
    crest = corr > np.percentile(corr, p["crest_pct"])
    resid = img - P.box(img, nr)
    lift = np.where(crest, resid, 0.0)

    # energy not explained by the local oriented periodic model
    ang, coh = _orient(img, um, p["fibre_hi_um"])
    resid_e = np.sqrt(np.maximum(P.box(resid*resid, ar), 0.0))*(1.0 - coh)

    return {
        "weave_amp": amp,
        "weave_fill": fill,
        "weave_lift": lift,
        "weave_resid": resid_e,
        "weave_period": coh,     # the trap: this IS the weave
    }


WEAVE_NAMES = ["weave_amp", "weave_fill", "weave_lift", "weave_resid", "weave_period"]


def main(n=12):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blind_pool = [t for s in bs for t in by[s]]
    rng = np.random.default_rng(11)

    tiles = []
    for t in P.warm([held[i] for i in rng.permutation(len(held))[:n*2]], verbose=False):
        c = P.crop_coverage(t)
        if c is not None and 0.02 < c < 0.7:
            tl = P.load_tile(t)
            if tl is not None:
                tiles.append(tl)
        if len(tiles) >= n:
            break
    negs = [P.load_tile(t) for t in P.warm(P.find_negatives(held, n=8), verbose=False)]
    negs = [t for t in negs if t is not None]
    blind = [P.load_tile(t) for t in P.warm(
        [blind_pool[i] for i in np.random.default_rng(0).permutation(len(blind_pool))[:5]],
        verbose=False)]
    blind = [t for t in blind if t is not None]
    print(f"{len(tiles)} text tiles, {len(negs)} verified-blank, {len(blind)} blind\n")
    if len(tiles) < 4:
        print("not enough tiles"); return

    print(f"{'feature':14s} {'ink r':>8s} {'signif':>7s} {'partial':>8s} "
          f"{'blank':>7s} {'blind':>7s}   verdict")
    print("-"*70)
    rows = []
    for nm in WEAVE_NAMES:
        rs, ps, pr = [], [], []
        for tile in tiles:
            f = weave_features(tile).get(nm)
            if f is None:
                continue
            s = P.score_vs_ink(f, tile, nulls=40)
            if s:
                rs.append(s["r"]); ps.append(s["p"])
            sp = P.score_partial(f, tile, nulls=12)
            if sp:
                pr.append(abs(sp["r"]))
        if len(rs) < 4:
            print(f"{nm:14s} too few tiles"); continue
        rs = np.array(rs)
        sign = 1.0 if np.median(rs) > 0 else -1.0
        med = float(np.median(sign*rs))
        nb = P.neg_control(lambda tl, _n=nm: weave_features(tl).get(_n), negs)
        bl = []
        for tile in blind:
            f = weave_features(tile).get(nm)
            if f is None:
                continue
            s = P.score_vs_ink(f, tile, nulls=1)
            if s:
                bl.append(abs(s["r"]))
        blm = float(np.median(bl)) if bl else None
        prm = float(np.median(pr)) if pr else None
        alive = (abs(med) >= 0.20 and prm is not None and prm >= 0.15
                 and (nb is None or nb <= 0.12) and (blm is None or blm <= 0.15)
                 and nm != "weave_period")
        rows.append(dict(feature=nm, ink_r=med, partial=prm, blank=nb, blind=blm,
                         n=len(rs), alive=bool(alive)))
        g = lambda x: "--" if x is None else f"{x:.3f}"
        note = "  (control feature)" if nm == "weave_period" else ""
        print(f"{nm:14s} {med:+8.3f} {float((np.array(ps)<0.05).mean())*100:6.0f}% "
              f"{g(prm):>8s} {g(nb):>7s} {g(blm):>7s}   "
              f"{'WORTH THE BATTERY' if alive else 'dead'}{note}")

    json.dump(rows, open(os.path.join(OUT, "weave_test.json"), "w"), indent=1)
    wp = next((r for r in rows if r["feature"] == "weave_period"), None)
    if wp:
        print(f"\nreference: weave_period (the papyrus structure itself) scores "
              f"{wp['ink_r']:+.3f} against ink.")
        print("Any real ink feature has to beat that, or it is just reading the weave.")
    return rows


if __name__ == "__main__":
    t0 = time.time()
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
    print(f"{time.time()-t0:.0f}s")
