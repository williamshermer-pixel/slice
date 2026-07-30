"""PARTICLES — hunt the lead, not the layer.

THE HYPOTHESIS, AND WHY IT IS NOT ANOTHER TEXTURE MEASURE

Brun et al., PNAS 113:3751 (2016), "Revealing metallic ink in Herculaneum
papyri", found lead in the ink of Herculaneum papyri at ~84 +/- 5 ug/cm2 — a
concentration they argued was too high to be contamination and was therefore
deliberate. Herculaneum ink is not simply carbon.

Work the number. Spread through a 15 um ink layer, 84 ug/cm2 is

    84e-6 g / 1.5e-3 cm3  =  0.056 g/cm3  of lead

against metallic lead at 11.34 g/cm3, i.e. about 0.5% by VOLUME. Lead's mass
attenuation coefficient near 50-60 keV is roughly 30x carbon's, so a uniform
leaded layer should be several times more attenuating than the papyrus around
it — an enormous, obvious CT signal.

But the measured density correlation in this project is r = +0.002 with 88%
distribution overlap. Both cannot be true of a UNIFORM layer.

The resolution is that the lead is almost certainly PARTICULATE — discrete
grains, not an even film. And that changes everything about how to look, because
every one of the fourteen mechanisms tried so far AVERAGES: box filters at
250-1500 um, band means over depth, gradients, structure tensors, PCA. Averaging
a few very bright grains into a 750 um neighbourhood destroys them. The signal,
if it exists, is in the extreme UPPER TAIL of the voxel distribution, and the
tail is precisely what a mean throws away.

So this looks for rare bright voxels and asks where they are.

TWO INDEPENDENT DISCRIMINATORS

  1 SPATIAL   does speck density track the published ink map?
  2 DEPTH     do the specks sit AT THE SHEET SURFACE, where ink was applied,
              or are they scattered through the full thickness?

The second is the strong one and it is nearly free. Mineral grit and beam
artefacts have no reason to prefer the surface. Ink does. A depth histogram of
speck positions, peaked at the sheet face, is hard to explain any other way —
and it does not depend on the ink map at all, so it cannot be a labelling
artefact.

Usage: python3 particles.py [n_tiles] [percentile]
"""
import os, sys, json, time
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "particles")
FIND = os.path.join(HERE, "..", "findings")
os.makedirs(OUT, exist_ok=True)

PCTS = [99.0, 99.5, 99.9, 99.99]
BAND = 20            # layers each side of the sheet peak to search


def speck_field(tile, pct, band=BAND):
    """Count of extreme-bright voxels in each (y,x) column, and their depths.

    Threshold is per-tile, on non-air voxels only, so it adapts to each scan's
    exposure rather than assuming a global grey level.
    """
    pk = tile["pk"]
    v = P.layers(tile, pk-band, pk+band+1)
    if v.size == 0:
        return None, None, None
    solid = v[v > 0]
    if solid.size < 1000:
        return None, None, None
    thr = float(np.percentile(solid, pct))
    hot = (v >= thr) & (v > 0)
    density = hot.sum(0).astype(np.float32)          # per column
    zprof = hot.sum(axis=(1, 2)).astype(np.float32)  # per depth layer
    return density, zprof, thr


def main(n=8, pct=None):
    tg = P.targets()
    by, um, ts, hs, bs = P.strata(tg)
    held = [t for s in hs for t in by[s]]
    blind_pool = [t for s in bs for t in by[s]]
    rng = np.random.default_rng(77)

    cand = P.warm([held[i] for i in rng.permutation(len(held))[:n*3]], verbose=False)
    tiles = []
    for t in cand:
        c = P.crop_coverage(t)
        if c is not None and 0.03 < c < 0.6:
            tl = P.load_tile(t)
            if tl is not None:
                tiles.append(tl)
        if len(tiles) >= n:
            break
    negs = [P.load_tile(t) for t in P.warm(P.find_negatives(held, n=6), verbose=False)]
    negs = [t for t in negs if t is not None]
    blind = [P.load_tile(t) for t in P.warm(
        [blind_pool[i] for i in np.random.default_rng(0).permutation(len(blind_pool))[:5]],
        verbose=False)]
    blind = [t for t in blind if t is not None]
    print(f"{len(tiles)} text tiles, {len(negs)} blank, {len(blind)} blind\n")
    if not tiles:
        return

    pcts = [pct] if pct else PCTS
    rows = []
    print("1  SPATIAL — does speck density track the ink map?\n")
    print(f"{'percentile':>11s} {'ink r':>8s} {'signif':>7s} {'blank':>8s} {'blind':>8s} "
          f"{'specks/tile':>12s}")
    for p in pcts:
        rs, ps, cnt = [], [], []
        for tile in tiles:
            d, _, _ = speck_field(tile, p)
            if d is None:
                continue
            s = P.score_vs_ink(d, tile, nulls=40)
            if s:
                rs.append(s["r"]); ps.append(s["p"]); cnt.append(float(d.sum()))
        if len(rs) < 3:
            print(f"{p:11.2f} {'too few':>8s}")
            continue
        nb = []
        for tile in negs:
            d, _, _ = speck_field(tile, p)
            if d is None:
                continue
            fb, sub = P._align(d, tile)
            if fb is None or fb.std() < 1e-9 or sub.std() < 1e-9:
                continue
            nb.append(abs(float(np.corrcoef(fb.ravel(), sub.ravel())[0, 1])))
        bl = []
        for tile in blind:
            d, _, _ = speck_field(tile, p)
            if d is None:
                continue
            s = P.score_vs_ink(d, tile, nulls=1)
            if s:
                bl.append(abs(s["r"]))
        med = float(np.median(rs))
        row = dict(percentile=p, ink_r=med, frac_signif=float((np.array(ps) < 0.05).mean()),
                   blank=float(np.median(nb)) if nb else None,
                   blind=float(np.median(bl)) if bl else None,
                   specks_per_tile=float(np.median(cnt)), n=len(rs))
        rows.append(row)
        f = lambda x: "--" if x is None else f"{x:.3f}"
        print(f"{p:11.2f} {med:+8.3f} {row['frac_signif']*100:6.0f}% "
              f"{f(row['blank']):>8s} {f(row['blind']):>8s} {row['specks_per_tile']:12.0f}")

    print("\n2  DEPTH — do the specks sit at the sheet surface?\n")
    print("   (this uses NO ink labels, so it cannot be a labelling artefact)")
    depth_rows = []
    for p in pcts:
        prof = None
        for tile in tiles:
            _, zp, _ = speck_field(tile, p)
            if zp is None or zp.sum() <= 0:
                continue
            q = zp/zp.sum()
            prof = q if prof is None else prof + q
        if prof is None:
            continue
        prof = prof/prof.sum()
        c = len(prof)//2
        # concentration in the middle third (the sheet face) vs the rest
        lo, hi = c - len(prof)//6, c + len(prof)//6 + 1
        core = float(prof[lo:hi].sum())
        expect = (hi-lo)/len(prof)
        depth_rows.append(dict(percentile=p, core_frac=core, expected=expect,
                               enrichment=core/max(expect, 1e-9)))
        print(f"   {p:6.2f}th  {core*100:5.1f}% of specks in the central third "
              f"(chance {expect*100:.1f}%)  enrichment x{core/max(expect,1e-9):.2f}")
    _plot(tiles, pcts[-1] if pcts else 99.9)

    json.dump(dict(spatial=rows, depth=depth_rows),
              open(os.path.join(FIND, "particles.json"), "w"), indent=1)
    print("\n" + "="*72)
    best = max(rows, key=lambda r: abs(r["ink_r"])) if rows else None
    if best:
        clean = (abs(best["ink_r"]) >= 0.20
                 and (best["blank"] is None or best["blank"] <= 0.12)
                 and (best["blind"] is None or best["blind"] <= 0.15))
        print(f"best spatial: {best['percentile']}th percentile, r={best['ink_r']:+.3f}, "
              f"blank {best['blank']}, blind {best['blind']}")
        print("WORTH THE FULL BATTERY" if clean else
              "does not clear the bar — but check the depth enrichment above,\n"
              "which is a separate and label-free line of evidence.")
    return rows, depth_rows


def _plot(tiles, pct):
    """Speck map beside the ink map, and the depth histogram."""
    try:
        S = 300
        rows = []
        for tile in tiles[:3]:
            d, zp, _ = speck_field(tile, pct)
            if d is None:
                continue
            fb, sub = P._align(d, tile)
            if fb is None:
                continue
            def n8(a):
                a = np.asarray(a, np.float32)
                l, h = np.percentile(a, 2), np.percentile(a, 99.5)
                return np.clip((a-l)/max(h-l, 1e-6)*255, 0, 255).astype(np.uint8)
            det, ink = n8(fb), np.clip(sub, 0, 255).astype(np.uint8)
            rgb = np.dstack([det, ink, np.zeros_like(det)])
            row = Image.new("RGB", (3*S+20, S), (10, 10, 11))
            for i, im in enumerate([Image.fromarray(det), Image.fromarray(ink),
                                    Image.fromarray(rgb)]):
                row.paste(im.convert("RGB").resize((S, S), Image.LANCZOS), (i*(S+10), 0))
            rows.append((row, tile["scroll"], zp))
        if not rows:
            return
        sheet = Image.new("RGB", (3*S+20, 30 + len(rows)*(S+130)), (10, 10, 11))
        d0 = ImageDraw.Draw(sheet)
        d0.text((6, 8), f"SPECK DENSITY at {pct}th percentile   "
                        f"[specks | published ink | overlay]", fill=(233, 229, 219))
        for i, (row, scroll, zp) in enumerate(rows):
            y = 30 + i*(S+130)
            sheet.paste(row, (0, y))
            d0.text((6, y+S+4), f"{scroll}   depth histogram of specks "
                                f"(centre = sheet face):", fill=(139, 139, 148))
            if zp is not None and zp.sum() > 0:
                q = zp/zp.max()
                for xi, val in enumerate(q):
                    x0 = 6 + int(xi*(3*S)/len(q))
                    x1 = 6 + int((xi+1)*(3*S)/len(q)) - 1
                    h = int(val*90)
                    col = (200, 151, 31) if abs(xi-len(q)//2) <= len(q)//6 else (90, 90, 98)
                    d0.rectangle([x0, y+S+118-h, max(x1, x0+1), y+S+118], fill=col)
                cx = 6 + int((len(q)//2)*(3*S)/len(q))
                d0.line([cx, y+S+20, cx, y+S+118], fill=(233, 229, 219))
        sheet.save(os.path.join(OUT, "specks.png"))
        print(f"\n   image: {os.path.join(OUT, 'specks.png')}")
    except Exception as e:
        print("   (plot failed:", e, ")")


if __name__ == "__main__":
    a = sys.argv[1:]
    t0 = time.time()
    main(int(a[0]) if a else 8, float(a[1]) if len(a) > 1 else None)
    print(f"{time.time()-t0:.0f}s")
