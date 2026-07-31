"""LINE HUNT — stop looking for letters, look for LINES OF TEXT.

Every search in this project hunted letter-sized blobs. That is the wrong
scale twice over: the model's field of view is 0.58 mm (a third of a letter),
and undiscovered writing does not arrive as isolated letters — it arrives as
LINES, parallel bands at the scribe's measured pitch running across a column.

A line is 20+ letters of evidence integrated into one structure, so it
survives per-letter weakness that kills a blob search. It also has a signature
damage does not: PERIODICITY. Real text repeats at one pitch; a stain does not.

Method, on maps we already hold:
  1. project the map's uncalled region onto the y axis
  2. autocorrelate that profile — text shows a peak at the measured line pitch
  3. score the peak against a spatial null (roll the map, same statistics,
     registration destroyed) — the same gate that killed 11 blob candidates

  python3 tools/line_hunt.py            # PHerc0139 by default
  SCROLL=PHercParis4 OUTDIR=scroll1 python3 tools/line_hunt.py
"""
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D

N_ROLL = 32
RNG = np.random.default_rng(37)


def line_score(field, pitch_px):
    """Autocorrelation of the row-projection at the scribe's line pitch.

    Returns (score, best_lag). Score is the autocorrelation at the best lag
    within +/-25% of the measured pitch, minus the local background — so a
    broad smear scores ~0 and only genuine periodicity scores high.
    """
    proj = field.sum(1).astype(np.float64)
    proj -= proj.mean()
    if proj.std() < 1e-9:
        return 0.0, 0
    ac = np.correlate(proj, proj, "full")[len(proj) - 1:]
    ac /= max(ac[0], 1e-12)
    lo, hi = int(pitch_px * 0.75), int(pitch_px * 1.25)
    hi = min(hi, len(ac) - 1)
    if hi <= lo + 2:
        return 0.0, 0
    band = ac[lo:hi]
    lag = lo + int(band.argmax())
    # background: the autocorrelation away from any harmonic of the pitch
    far = np.concatenate([ac[int(pitch_px * 0.3):lo],
                          ac[hi:min(len(ac), int(pitch_px * 1.9))]])
    bg = float(np.median(far)) if far.size else 0.0
    return float(band.max() - bg), lag


def main():
    pitch = D.PITCH
    floor = json.load(open(os.path.join(D.LB, "floor.json")))["floor"]
    print(f"{D.SCROLL} · line pitch {pitch:.0f} px ({pitch/D.MM:.2f} mm) · "
          f"floor {floor:.3f}")
    print(f"searching for PERIODIC LINE STRUCTURE in uncalled regions\n")
    print(f"{'segment':30} {'aim':>5} {'score':>7} {'lag':>6} {'mm':>6}")
    hits = []
    for mp in sorted(glob.glob(os.path.join(D.LB, "map_s*.npy"))):
        tag = os.path.basename(mp)[4:-4]
        mf = os.path.join(D.LB, f"meta_{tag}.json")
        if not os.path.exists(mf):
            continue
        meta = json.load(open(mf))
        try:
            pub = D.pub_crop(meta)
        except Exception:
            continue
        ours = np.load(mp)
        # the hunting ground: our confident response where nothing was called
        field = np.where((pub < 60) & (ours >= floor), ours, 0.0)
        if (field > 0).mean() < 0.001:
            continue
        sc, lag = line_score(field, pitch)
        if sc <= 0:
            continue
        print(f"{meta['seg'].split('/')[-2][:28]:30} {meta['aim']:5.2f} "
              f"{sc:7.3f} {lag:6d} {lag/D.MM:6.2f}")
        hits.append((tag, meta, field, sc, lag))

    if not hits:
        print("\nno periodic structure anywhere — nothing to null-test")
        return
    hits.sort(key=lambda h: -h[3])
    print(f"\nspatial null on the top {min(6, len(hits))}:")
    survivors = []
    for tag, meta, field, sc, lag in hits[:6]:
        beat = 0
        for _ in range(N_ROLL):
            dy = int(RNG.integers(64, field.shape[0] - 64))
            dx = int(RNG.integers(64, field.shape[1] - 64))
            rl = np.roll(np.roll(field, dy, 0), dx, 1)
            s2, _ = line_score(rl, pitch)
            if s2 >= sc:
                beat += 1
        p = (beat + 1) / (N_ROLL + 1)
        ok = p < 0.05
        survivors.append((tag, meta, sc, lag, p, ok))
        print(f"  {meta['seg'].split('/')[-2][:26]:28} score {sc:.3f} "
              f"lag {lag/D.MM:.2f} mm · nulls>= {beat}/{N_ROLL} p={p:.3f} "
              f"{'SURVIVES' if ok else 'dead'}")
    live = [s for s in survivors if s[5]]
    print(f"\n{len(live)} survive")
    json.dump([dict(tag=t, seg=m["seg"], score=round(sc, 4),
                    lag_mm=round(lag / D.MM, 3), p=round(p, 4), survives=ok)
               for t, m, sc, lag, p, ok in survivors],
              open(os.path.join(D.LB, "line_hunt.json"), "w"), indent=1)
    if live:
        print("Render these before believing anything: tools/render_3d.py "
              "style figure on the surviving windows.")


if __name__ == "__main__":
    main()
