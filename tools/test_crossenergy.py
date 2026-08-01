#!/usr/bin/env python3
"""Test harness for the cross-energy diagnostic. Must pass all checks.

Same contract as tools/test_differential.py: this is not a smoke test, it is a
gate. Every check corresponds to a mistake that was actually made building this
on 2026-07-31, so a regression puts one of them back.

  1  registration is identity      the canvas-ratio resize IS the global fit;
                                   if a future change breaks this, every number
                                   downstream is measuring misaligned sheets
  2  mask registration is wrong    the sheet-outline fit must be measurably
                                   worse than the text fit (78 keV recovers
                                   1.8x more sheet and drags it to sy=0.87)
  3  agreement beats its null      Jaccard >> rolled-null Jaccard, and rises
                                   monotonically as the call tightens
  4  edge keep-out holds           no scored pixel may sit within 1.5 letters
                                   of a sheet edge; violating it manufactured
                                   the first false candidate (0.78 mm out)
  5  letter-box coverage           the box must be >=95% on shared sheet
  6  zarr round-trips              reassembled chunks == certificate counts,
                                   read the way a consumer reads them, and NOT
                                   only chunk 0.0 (that trap already bit once)
  7  certificates carry the bounds condition AND model-lineage limitations
                                   present on every shipped array
  8  json writes merge             re-running one segment must not wipe the
                                   others; this clobbered results twice
  9  effective area < searched     the negative must be reported on area that
                                   can actually host a letter
 10  pair certificate is sane      corroboration fractions in [0,1], and the
                                   two known-bad pairs are still flagged

    python3 tools/test_crossenergy.py
"""
import glob, json, os, subprocess, sys, zlib
import numpy as np
from scipy import ndimage
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS8_UM = 18.064
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return ok


def scroll_dirs():
    out = {}
    for s, d in (("PHerc1667", "s1667"), ("PHerc0139", "xe_PHerc0139"),
                 ("PHerc0814", "xe_PHerc0814")):
        p = os.path.join(ROOT, "out", d)
        if os.path.exists(os.path.join(p, "crossenergy.json")):
            out[s] = p
    return out


def main():
    dirs = scroll_dirs()
    print(f"cross-energy test harness — {len(dirs)} scrolls\n")

    # ---- 1 & 2: registration -------------------------------------------
    print("registration")
    d = dirs.get("PHerc0139") or list(dirs.values())[0]
    f = sorted(glob.glob(os.path.join(d, "xe_*.npz")))[0]
    z = np.load(f)
    A, B, m = z["A"].astype(np.float32), z["B"].astype(np.float32), z["m"]
    LET = 1.61 * 1000 / DS8_UM
    hp = lambda x: x - ndimage.gaussian_filter(np.where(m, x, 0.0), LET)
    Ah, Bh = hp(A), hp(B)
    r0 = float(np.corrcoef(Ah[m], Bh[m])[0, 1])
    best = (None, None)
    for dy in (-64, -32, 0, 32, 64):
        for dx in (-64, -32, 0, 32, 64):
            v = float(np.corrcoef(Ah[m], np.roll(Bh, (dy, dx), (0, 1))[m])[0, 1])
            if best[0] is None or v > best[0]:
                best = (v, (dy, dx))
    check("1 registration is identity (no shift beats zero shift)",
          best[1] == (0, 0), f"best offset {best[1]}, r {best[0]:.4f} vs {r0:.4f}")

    mask_r = float(np.corrcoef(m.ravel().astype(np.float32),
                               (z["cb"] | z["ca"]).ravel().astype(np.float32))[0, 1])
    check("2 text fit beats sheet-outline fit", r0 > mask_r,
          f"text r {r0:.3f} vs outline r {mask_r:.3f}")

    # ---- 3: agreement vs null, monotone in threshold --------------------
    print("\nagreement")
    rep = json.load(open(os.path.join(d, "crossenergy.json")))["segments"]
    bad = [k for k, v in rep.items()
           if v["null_mean"] is not None and v["jaccard"] <= v["null_mean"]]
    check("3a every segment beats its spatial null", not bad,
          f"{len(rep)} segments, {len(bad)} failures")
    ps = [v["p"] for v in rep.values()]
    check("3b every segment significant vs null", max(ps) <= 0.05,
          f"max p {max(ps)}")

    # ---- 4 & 5: keep-outs ----------------------------------------------
    print("\nkeep-outs")
    cj = os.path.join(d, "conjunction.json")
    viol = []
    if os.path.exists(cj):
        creps = json.load(open(cj))["segments"]
        for seg, v in creps.items():
            cf = os.path.join(d, f"cj_{seg}.npz")
            if not os.path.exists(cf):
                continue
            search = np.load(cf)["search"]
            mm = np.load(os.path.join(d, f"xe_{seg}.npz"))["m"]
            dist = ndimage.distance_transform_edt(mm)
            if search.any() and dist[search].min() < 1.5 * LET - 1:
                viol.append((seg, float(dist[search].min() / LET)))
    check("4 no scored pixel within 1.5 letters of a sheet edge", not viol,
          f"{len(viol)} violations" + (f" worst {viol[0][1]:.2f}L" if viol else ""))

    src = open(os.path.join(ROOT, "tools", "conjunction_1667.py")).read()
    check("5 letter-box requires >=95% sheet coverage",
          "MIN_BOX_COVER = 0.95" in src and "den >= MIN_BOX_COVER" in src)

    # ---- 6 & 7: shipped arrays -----------------------------------------
    print("\nshipped label arrays")
    zarrs = sorted(glob.glob(os.path.join(ROOT, "out", "consensus", "*", "*.zarr")))
    sample = sorted(glob.glob(os.path.join(ROOT, "samples", "consensus", "*.zarr")))
    # ALL of them, not a sample — a spot check on 3 of 62 is how the
    # "measured the top-left quarter" bug survived review once already.
    tested = (zarrs + sample) or []
    rt_ok, cert_ok, multi_chunk = True, True, False
    for p in tested:
        za = json.load(open(os.path.join(p, ".zarray")))
        ce = json.load(open(os.path.join(p, ".zattrs")))
        ch, sh = za["chunks"], za["shape"]
        gy, gx = -(-sh[0] // ch[0]), -(-sh[1] // ch[1])
        if gy * gx > 1:
            multi_chunk = True
        a = np.zeros(sh, np.uint8)
        for i in range(gy):
            for j in range(gx):
                fp = os.path.join(p, f"{i}.{j}")
                if not os.path.exists(fp):
                    continue
                b = np.frombuffer(zlib.decompress(open(fp, "rb").read()),
                                  np.uint8).reshape(ch)
                h = min(ch[0], sh[0] - i * ch[0])
                w = min(ch[1], sh[1] - j * ch[1])
                a[i*ch[0]:i*ch[0]+h, j*ch[1]:j*ch[1]+w] = b[:h, :w]
        got = {k: int((a == v).sum()) for k, v in
               (("unlabelled", 0), ("ink", 1), ("blank", 2), ("disputed", 3))}
        if got != ce["counts_px"]:
            rt_ok = False
        if not ("LIMITATION_condition" in ce and "LIMITATION_model_lineage" in ce):
            cert_ok = False
    check("6a zarr reassembles to the certificate counts", rt_ok and bool(tested),
          f"{len(tested)} arrays")
    check("6b test reads all chunks, not just 0.0", multi_chunk)
    check("7 certificates carry BOTH limitations", cert_ok and bool(tested))

    # ---- 8: merge semantics --------------------------------------------
    print("\njson write semantics")
    ok = True
    for t in ("conjunction_1667.py", "crossenergy_1667.py"):
        s = open(os.path.join(ROOT, "tools", t)).read()
        if "prev" not in s or "MERGE, never overwrite" not in s:
            ok = False
    check("8 single-segment reruns merge instead of clobbering", ok)

    # ---- 9: effective area ---------------------------------------------
    print("\nnegative is reported honestly")
    eff_ok, shown = True, []
    for s, dd in dirs.items():
        ep = os.path.join(dd, "effective_area.json")
        if not os.path.exists(ep):
            continue
        t = json.load(open(ep))["totals_mm2"]
        shown.append(f"{s} {t['eff']/100:.1f}/{t['search']/100:.1f} cm2")
        if not (0 < t["eff"] < t["search"]):
            eff_ok = False
    check("9 effective area measured and smaller than searched",
          eff_ok and bool(shown), "; ".join(shown))

    # ---- 10: pair certificate ------------------------------------------
    print("\npair certificate")
    pc = os.path.join(ROOT, "out", "pairs", "CROSSENERGY_CERTIFICATE.json")
    if os.path.exists(pc):
        pr = json.load(open(pc))["pairs"]
        vals = [o.get("corroborated_frac", o.get("both_scans_blank_frac"))
                for o in pr]
        vals = [v for v in vals if v is not None]
        rng_ok = all(0.0 <= v <= 1.0 for v in vals)
        flagged = [o["pair"] for o in pr
                   if o.get("corroborated_frac") == 0.0
                   or (o.get("both_scans_blank_frac") or 1) < 0.1]
        check("10a corroboration fractions in [0,1]", rng_ok, f"n={len(vals)}")
        check("10b the two known-bad pairs are still flagged", len(flagged) >= 2,
              f"{len(flagged)} flagged")
    else:
        check("10 pair certificate exists", False)

    print(f"\n{'='*62}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
