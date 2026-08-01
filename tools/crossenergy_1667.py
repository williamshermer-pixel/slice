#!/usr/bin/env python3
"""Cross-energy consensus on PHerc1667 — an artifact filter that is physical,
not statistical.

Every curated 1667 segment was scanned TWICE and published TWICE:

  59 keV  flattened to `1.129um-...-L1` (2.258 um/voxel, 116 layers),
          ink map recipe `mrg20736-1um-s1z2`, dated 2026-07-09
  78 keV  flattened to `2.399um-...`    (2.399 um/voxel, 109 layers),
          ink map recipe `new_canon_autoresearch_recipe`, dated 2026-04-17

Different photon energy, different reconstruction, different flattening run,
different model recipe, three months apart. The only thing they share is the
papyrus.

Why this matters here. Every candidate this project has killed died as an
artifact that survived spatial nulls AND independent replication, because both
runs shared one input volume — the 2026-07-29 differential (23/24 rolled copies
reproduced it) and the aimed-window family (pure box-filter edge geometry) both
died that way. Two energies do not share an input. Agreement between them is
evidence no null over a single map can supply.

Registration (measured, not assumed): the two canvases differ by exactly the
voxel ratio, and after resizing B onto A's canvas the best global fit is
sx=1.000 sy=1.000 dy=0 dx=0 — the flattenings share a UV layout. Residual local
warp is small (median 0 px, IQR ~45 px = 0.8 mm) and is taken out with a block
phase-correlation field. Registering on the sheet MASK instead is wrong: the
78 keV flattening recovers ~1.8x more sheet, so mask overlap drags the fit to a
false sy=0.87.

Everything is computed on ds8 published maps: 18.064 um/px, so 1667's measured
1.63 mm hand spans ~90 px. Calls are integrated over a letter-sized box, never
per-pixel (per-pixel recovers 10-12% of known letters; letter-box 78-98%).

Usage:
    python3 tools/crossenergy_1667.py            # all segments
    python3 tools/crossenergy_1667.py 20240304161941
"""
import os, sys, glob, json
import numpy as np
from scipy import ndimage
from PIL import Image

Image.MAX_IMAGE_PIXELS = None            # 200+ MP maps trip the bomb guard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Named for 1667 because that is where the method was built, but it runs on any
# scroll with two usable energies -- same pattern as differential_0139.py.
# Hands are band-FWHM (tools/measure_hand.py); component-based heights are wrong
# by 3-5x. Only scrolls with two INDEPENDENT energies fine enough to sample a
# 15 um ink layer are listed: 0343P/0500P2 have one usable scan, Paris4's two
# are both 78 keV.
HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc1667")
if SCROLL not in HANDS:
    raise SystemExit(f"no cross-energy pair / measured hand for {SCROLL}; "
                     f"known: {list(HANDS)}")
_DIRS = {"PHerc1667": "s1667"}           # 1667's results predate the naming
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))
PUB = os.path.join(OUT, "pub")

DS8_UM = 18.064                          # 2.258 um/px canvas map, downsampled 8x
LETTER_MM = HANDS[SCROLL]                # band-FWHM hand, tools/measure_hand.py
LETTER_PX = LETTER_MM * 1000.0 / DS8_UM  # ~90 px
BOX = max(3, int(round(0.7 * LETTER_PX)))  # letter-scale integration box
CALL_PCT = 90.0                          # each energy calls its own top decile
NULL_N = 24                              # rolled copies for the spatial null


def segments():
    out = {}
    for f in sorted(glob.glob(os.path.join(PUB, "*.jpg"))):
        seg = os.path.basename(f).split("-")[1]
        e = "59" if "1.129um" in f else "78"
        out.setdefault(seg, {})[e] = f
    return {k: v for k, v in sorted(out.items()) if len(v) == 2}


def load(path):
    return np.asarray(Image.open(path).convert("L")).astype(np.float32) / 255.0


def sheet(a):
    """Where the map is written at all. Outside the sheet it is exactly 0;
    JPEG ringing puts a little energy in the margin, so smooth and cut low."""
    return ndimage.uniform_filter(a, 33) > 0.02


def block_field(Ah, Bh, m, blk=512, min_sharp=10.0, max_shift=128):
    """Local displacement field from block phase correlation on letter-scale
    high-passed maps. Blocks that are mostly off shared sheet, flat, or whose
    correlation peak is not sharp are not trusted and are filled from the
    trusted median."""
    H, W = Ah.shape
    gy, gx = max(1, H // blk), max(1, W // blk)
    fy = np.zeros((gy, gx), np.float32)
    fx = np.zeros((gy, gx), np.float32)
    ok = np.zeros((gy, gx), bool)
    win = np.outer(np.hanning(blk), np.hanning(blk))
    for i in range(gy):
        for j in range(gx):
            sl = (slice(i * blk, i * blk + blk), slice(j * blk, j * blk + blk))
            a, b, mm = Ah[sl], Bh[sl], m[sl]
            if a.shape != (blk, blk) or mm.mean() < 0.6:
                continue
            if a.std() < 0.01 or b.std() < 0.01:
                continue
            R = np.fft.rfft2(a * win) * np.conj(np.fft.rfft2(b * win))
            mag = np.abs(R)
            C = np.fft.irfft2(np.where(mag > 1e-12, R / mag, 0), s=(blk, blk))
            k = np.unravel_index(np.argmax(C), C.shape)
            sharp = C[k] / (np.median(np.abs(C)) + 1e-9)
            dy = k[0] - blk if k[0] > blk // 2 else k[0]
            dx = k[1] - blk if k[1] > blk // 2 else k[1]
            if sharp < min_sharp or abs(dy) > max_shift or abs(dx) > max_shift:
                continue
            fy[i, j], fx[i, j], ok[i, j] = dy, dx, True
    if ok.sum() >= 3:
        fy[~ok], fx[~ok] = np.median(fy[ok]), np.median(fx[ok])
        fy, fx = ndimage.gaussian_filter(fy, 0.8), ndimage.gaussian_filter(fx, 0.8)
    return fy, fx, ok


def warp(B, fy, fx):
    H, W = B.shape
    FY = ndimage.zoom(fy, (H / fy.shape[0], W / fx.shape[1]), order=1)[:H, :W]
    FX = ndimage.zoom(fx, (H / fy.shape[0], W / fx.shape[1]), order=1)[:H, :W]
    if FY.shape != (H, W):
        FY = np.pad(FY, [(0, H - FY.shape[0]), (0, W - FY.shape[1])], mode="edge")
        FX = np.pad(FX, [(0, H - FX.shape[0]), (0, W - FX.shape[1])], mode="edge")
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return ndimage.map_coordinates(B, [yy + FY, xx + FX], order=1, mode="nearest")


def letter_response(a, m):
    """Letter-box integrated response, zero outside the sheet so the box does
    not average sheet against void at the edges."""
    a = np.where(m, a, 0.0)
    num = ndimage.uniform_filter(a, BOX)
    den = ndimage.uniform_filter(m.astype(np.float32), BOX)
    return np.where(den > 0.5, num / np.maximum(den, 1e-6), 0.0)


def overlap(ca, cb, m):
    """Jaccard of two call masks, restricted to shared sheet."""
    a, b = ca & m, cb & m
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(0)
    report = {}

    for seg, d in segments().items():
        if only and only not in seg:
            continue
        A = load(d["59"])
        B = load(d["78"])
        # canvas-ratio resize IS the global registration (measured: identity)
        Bz = ndimage.zoom(B, (A.shape[0] / B.shape[0], A.shape[1] / B.shape[1]),
                          order=1)[:A.shape[0], :A.shape[1]]
        if Bz.shape != A.shape:
            Bz = np.pad(Bz, [(0, A.shape[i] - Bz.shape[i]) for i in range(2)],
                        mode="edge")

        sa, sb = sheet(A), sheet(Bz)
        hp = lambda x: x - ndimage.gaussian_filter(x, LETTER_PX)
        fy, fx, ok = block_field(hp(A), hp(Bz), sa & sb)
        Bw = warp(Bz, fy, fx)
        sbw = warp(sb.astype(np.float32), fy, fx) > 0.5
        m = sa & sbw                       # shared sheet, post-registration

        if m.sum() < 10000:
            print(f"{seg}  shared sheet too small, skipped")
            continue

        La, Lb = letter_response(A, m), letter_response(Bw, m)
        ta, tb = np.percentile(La[m], CALL_PCT), np.percentile(Lb[m], CALL_PCT)
        ca, cb = (La >= ta) & m, (Lb >= tb) & m

        obs = overlap(ca, cb, m)
        # spatial null: roll B's calls by >= 3 letters. Preserves histogram and
        # autocorrelation, destroys registration. Pixel permutation is invalid.
        lo = int(3 * LETTER_PX)
        nulls = []
        for _ in range(NULL_N):
            sy = int(rng.integers(lo, max(lo + 1, m.shape[0] - lo)))
            sx = int(rng.integers(lo, max(lo + 1, m.shape[1] - lo)))
            nulls.append(overlap(ca, np.roll(cb, (sy, sx), (0, 1)), m))
        nulls = np.array(nulls)
        p = float((nulls >= obs).sum() + 1) / (NULL_N + 1)
        # If no rolled copy produced ANY overlap the ratio is unbounded, not
        # enormous: 1e-9 in the denominator once reported a 7.5e7x "enrichment"
        # on PHerc0814 20260225160055. Report it as undefined and let the
        # p-value carry the claim.
        nm = float(nulls.mean())
        enrich = round(obs / nm, 2) if nm > 1e-6 else None

        r_hp = float(np.corrcoef(hp(A)[m], hp(Bw)[m])[0, 1])
        both = float((ca & cb).sum() / m.sum())
        o59 = float((ca & ~cb).sum() / m.sum())
        o78 = float((cb & ~ca).sum() / m.sum())

        np.savez_compressed(
            os.path.join(OUT, f"xe_{seg}.npz"),
            A=A.astype(np.float16), B=Bw.astype(np.float16),
            m=m, ca=ca, cb=cb)

        report[seg] = dict(
            shape=[int(v) for v in A.shape],
            shared_sheet_pct=round(100 * float(m.mean()), 1),
            blocks_trusted=int(ok.sum()), letter_px=round(LETTER_PX, 1),
            box_px=BOX, r_letterscale=round(r_hp, 3),
            consensus_pct=round(100 * both, 2),
            only59_pct=round(100 * o59, 2), only78_pct=round(100 * o78, 2),
            jaccard=round(obs, 4), null_mean=round(float(nulls.mean()), 4),
            enrichment=enrich, p=round(p, 4))
        print(f"{seg}  shared {100*m.mean():4.1f}%  r {r_hp:+.3f}  "
              f"consensus {100*both:5.2f}%  only59 {100*o59:5.2f}%  "
              f"only78 {100*o78:5.2f}%  J {obs:.3f} vs null {nulls.mean():.3f} "
              f"= {('%.1fx' % enrich) if enrich else 'undef'}  p={p:.3f}")

    # MERGE, never overwrite. Re-running a single segment must not wipe the
    # rest — it did, twice: once here and once in conjunction_1667.py. Running
    # one 0814 segment left crossenergy.json holding 1 of 18, which then
    # silently produced 1 of 18 label certificates downstream.
    path = os.path.join(OUT, "crossenergy.json")
    prev = {}
    if os.path.exists(path):
        try:
            prev = json.load(open(path)).get("segments", {})
        except Exception:
            prev = {}
    prev.update(report)
    with open(path, "w") as f:
        json.dump(dict(um_per_px=DS8_UM, letter_mm=LETTER_MM,
                       call_pct=CALL_PCT, null_n=NULL_N, segments=prev), f,
                  indent=1)
    print(f"\nwrote {OUT}/crossenergy.json")


if __name__ == "__main__":
    main()
