"""CONDITION — is the scroll that was READ in the same state as the others?

THE QUESTION, AND WHY IT IS THE RIGHT ONE

Every detector this project has produced has died the same death: it scored
well on ink and just as well on blank papyrus, because "this sheet is
well-preserved" tracks "there is text here". That is a CONDITION confound. So
the obvious follow-up is the one nobody had asked: how much does condition
actually vary between these scrolls, and is PHercParis4 — Scroll 1, the one
that was read — simply in better shape than the rest?

It matters three ways:

  1 If Scroll 1 is in materially better condition, then anything tuned or
    validated with it in the pool is being flattered, and its held-out
    performance is not evidence about the other scrolls.
  2 If condition varies a lot BETWEEN scrolls, a single global detector is the
    wrong object, and the search should be stratified — per scroll, or with
    condition regressed out — rather than asked to be universal.
  3 The condition measures themselves are the confound. If they are measured
    they can be REMOVED, by partialling them out of the correlation, which
    turns the trap into a control.

WHAT IS MEASURED, ALL FROM THE VOLUMES THEMSELVES

  voxel_um       scan resolution. the governing number in this whole project.
  layers         depth samples through the sheet
  contrast       p98-p2 of the sheet image — how much signal there is at all
  noise_um       high-frequency residual of the height field, in microns.
                 this is the noise floor the ~9 um ink relief has to beat.
  corr_len       decorrelation distance. the reason letter-stacking failed.
  coverage       fraction of the published ink map that is ink
  fibre_aniso    how directional the sheet texture is — a proxy for weave
                 integrity, i.e. condition

No labels are used to compute any of these, so nothing here can leak.

Usage
    python3 condition.py [n_per_scroll]
"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "findings")
os.makedirs(OUT, exist_ok=True)

READ_SCROLL = "PHercParis4"       # Scroll 1 — the one with published letters


def measure(tile):
    um = tile["um"]
    img = P.mid_image(tile, 8)
    if (img > 0).mean() < 0.5:
        return None
    m = img[img > 0]
    contrast = float(np.percentile(m, 98) - np.percentile(m, 2))

    h, _ = P.height_map(tile, band=10)
    # noise floor: residual after removing everything coarser than a stroke
    hf = h - P.box(h, max(1, int(round(350.0/um/2))))
    noise_um = float(hf.std())

    row = img[img.shape[0]//2].astype(np.float32)
    row = row - row.mean()
    if row.std() < 1e-9:
        return None
    ac = np.correlate(row, row, mode="full")[len(row)-1:]
    ac = ac/max(ac[0], 1e-9)
    below = np.where(ac[:128] < 1/np.e)[0]
    corr_len = int(below[0]) if len(below) else 128

    gy, gx = np.gradient(img)
    r = max(2, int(round(600.0/um/2)))
    Jxx, Jyy, Jxy = P.box(gx*gx, r), P.box(gy*gy, r), P.box(gx*gy, r)
    den = np.maximum(Jxx+Jyy, 1e-6)
    aniso = float((np.sqrt((Jxx-Jyy)**2 + 4*Jxy**2)/den).mean())

    return dict(voxel_um=um, layers=int(tile["vol8"].shape[0]),
                contrast=contrast, noise_um=noise_um,
                corr_len_px=corr_len, corr_len_um=corr_len*um,
                fibre_aniso=aniso,
                coverage=float((tile["ink"] > 128).mean()))


def main(n_per=6):
    tg = P.targets()
    by = {}
    for t in tg:
        by.setdefault(t["scroll"], []).append(t)

    rows = {}
    for sc in sorted(by):
        rng = np.random.default_rng(4)
        pick = [by[sc][i] for i in rng.permutation(len(by[sc]))[:n_per]]
        pick = P.warm(pick, verbose=False)
        ms = []
        for t in pick:
            tile = P.load_tile(t)
            if tile is None:
                continue
            m = measure(tile)
            if m:
                ms.append(m)
        if not ms:
            continue
        agg = {k: float(np.median([m[k] for m in ms])) for k in ms[0]}
        agg["n_tiles"] = len(ms)
        rows[sc] = agg
        print(f"  {sc:14s} n={len(ms)}  {agg['voxel_um']:.3f}um  "
              f"layers={agg['layers']:.0f}  contrast={agg['contrast']:.1f}  "
              f"noise={agg['noise_um']:.2f}um  corr={agg['corr_len_um']:.0f}um  "
              f"aniso={agg['fibre_aniso']:.3f}  cov={agg['coverage']:.3f}",
              flush=True)

    if not rows:
        print("no measurements"); return

    print("\n" + "="*78)
    print("IS THE READ SCROLL DIFFERENT?")
    print("="*78)
    if READ_SCROLL not in rows:
        print(f"{READ_SCROLL} not in the measured set")
    else:
        r = rows[READ_SCROLL]
        others = {k: v for k, v in rows.items() if k != READ_SCROLL}
        for key, label, better in [
            ("voxel_um", "scan resolution (um/voxel)", "lower"),
            ("contrast", "sheet contrast", "higher"),
            ("noise_um", "height noise floor (um)", "lower"),
            ("corr_len_um", "correlation length (um)", "lower"),
            ("fibre_aniso", "fibre anisotropy", "higher"),
        ]:
            o = np.median([v[key] for v in others.values()])
            rv = r[key]
            if o == 0:
                continue
            ratio = rv/o
            if better == "lower":
                verdict = "BETTER" if ratio < 0.9 else ("worse" if ratio > 1.1 else "same")
            else:
                verdict = "BETTER" if ratio > 1.1 else ("worse" if ratio < 0.9 else "same")
            print(f"  {label:30s} read={rv:9.3f}  others={o:9.3f}  "
                  f"x{ratio:5.2f}  -> read scroll is {verdict}")

        # the number that governs everything, restated per scroll
        print("\n  ink layer is ~15 um. voxels through it:")
        for sc in sorted(rows):
            v = 15.0/rows[sc]["voxel_um"]
            mark = "  <-- READ" if sc == READ_SCROLL else ""
            flag = "" if v >= 3 else "   (below the ~3 needed to resolve it at all)"
            print(f"    {sc:14s} {v:5.1f} voxels{flag}{mark}")

    # spread between scrolls, which is what decides stratify-or-not
    print("\n" + "="*78)
    print("HOW MUCH DOES CONDITION VARY BETWEEN SCROLLS?")
    print("="*78)
    for key in ["contrast", "noise_um", "corr_len_um", "fibre_aniso"]:
        v = np.array([rows[s][key] for s in rows])
        spread = v.max()/max(v.min(), 1e-9)
        print(f"  {key:16s} min={v.min():9.3f}  max={v.max():9.3f}  "
              f"spread x{spread:.1f}"
              f"{'   <-- large; a single global detector is the wrong object' if spread > 2 else ''}")

    out = os.path.join(OUT, "condition.json")
    json.dump(rows, open(out, "w"), indent=1)
    print(f"\nwritten {out}")
    return rows


if __name__ == "__main__":
    t0 = time.time()
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
    print(f"{time.time()-t0:.0f}s")
