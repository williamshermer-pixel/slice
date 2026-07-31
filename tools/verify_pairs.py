"""VERIFY AND GATE the image/label pairs — the QC step for villa #192.

#192 asks for "as-accurate-as-possible" and "high quality" labels. That is a
claim, so it gets measured, and pairs that do not carry real supervision are
REMOVED rather than padded into the count. A set of 20 pairs that each teach
something beats 40 where half are empty.

Checks, per pair:
  structure   image/ and label/ present, identical shape, licence file,
              quality certificate (floor, blank FPR, condition-control AUC)
  content     an ink pair needs resolved ink columns; a blank pair needs
              certified-blank volume. Empty is not shippable.
  TRUE 3D     ink depth must VARY across the crop (sd > 1 layer, >2 distinct
              depth centres) — this is the requirement v1 failed, so it is
              enforced here rather than trusted.

Writes MANIFEST.json (per-pair statistics, for anyone auditing the set) and,
with PRUNE=1, deletes what fails.

  python3 tools/verify_pairs.py            # report only
  PRUNE=1 python3 tools/verify_pairs.py    # report + remove failures
"""
import json, os, shutil, sys, zlib
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = os.path.join(ROOT, "out", "pairs")
PRUNE = os.environ.get("PRUNE") == "1"
MIN_INK_COLS = 400          # a crop worth training on
MIN_BLANK_FRAC = 0.02       # 2% certified absence
MIN_DEPTH_SD = 1.0          # layers — proves depth is not projected
MIN_DEPTH_LEVELS = 3


def read_chunk(d, arr):
    za = json.loads(open(os.path.join(d, arr, ".zarray")).read())
    raw = zlib.decompress(open(os.path.join(d, arr, "0.0.0"), "rb").read())
    return np.frombuffer(raw, np.uint8).reshape(za["chunks"]), za


def check(d):
    fail = []
    try:
        lab, zl = read_chunk(d, "label")
        img, zi = read_chunk(d, "image")
    except Exception as e:
        return None, [f"unreadable: {e}"]
    at = json.loads(open(os.path.join(d, "label", ".zattrs")).read())
    if zl["shape"] != zi["shape"]:
        fail.append("image/label shape mismatch")
    if not os.path.exists(os.path.join(d, "LICENCE-DATA.txt")):
        fail.append("missing data licence")
    for k in ("floor", "floor_blank_fpr", "condition_control_auc"):
        if not at.get(k):
            fail.append(f"missing certificate field {k}")
    if img.std() < 3:
        fail.append("image is flat — not real papyrus")

    ink = lab == 1
    has = ink.any(0)
    ncol = int(has.sum())
    sd, nlev = 0.0, 0
    if ncol:
        zz = np.arange(lab.shape[0])[:, None, None]
        cen = ((ink * zz).sum(0) / np.maximum(ink.sum(0), 1))[has]
        sd = float(cen.std())
        nlev = len(set(np.round(cen).astype(int).tolist()))
    blank = float((lab == 2).mean())
    amb = int((lab == 3).any(0).sum())
    kind = at.get("pair_kind", "?")

    if kind == "ink":
        if ncol < MIN_INK_COLS:
            fail.append(f"only {ncol} resolved ink columns (<{MIN_INK_COLS})")
        elif sd < MIN_DEPTH_SD or nlev < MIN_DEPTH_LEVELS:
            fail.append(f"depth does not vary (sd {sd:.1f}, {nlev} levels) "
                        "— would be a projection")
    elif kind == "blank":
        if blank < MIN_BLANK_FRAC:
            fail.append(f"only {100*blank:.1f}% certified blank "
                        f"(<{100*MIN_BLANK_FRAC:.0f}%)")
    stats = dict(pair=os.path.basename(d), kind=kind, ink_columns=ncol,
                 depth_sd_layers=round(sd, 2), depth_levels=nlev,
                 ambiguous_columns=amb, certified_blank_frac=round(blank, 4),
                 shape=zl["shape"],
                 condition_control_auc=at.get("condition_control_auc"),
                 floor=at.get("floor"))
    return stats, fail


def main():
    if not os.path.isdir(PAIRS):
        sys.exit("no out/pairs — run tools/make_pairs.py first")
    kept, dropped = [], []
    for scroll in sorted(os.listdir(PAIRS)):
        sd = os.path.join(PAIRS, scroll)
        if not os.path.isdir(sd):
            continue
        for name in sorted(os.listdir(sd)):
            d = os.path.join(sd, name)
            if not os.path.isdir(d):
                continue
            stats, fail = check(d)
            if fail:
                dropped.append((name, fail))
                if PRUNE:
                    shutil.rmtree(d)
            else:
                stats["scroll"] = scroll
                kept.append(stats)

    print(f"{len(kept)} pairs PASS · {len(dropped)} fail"
          + (" (removed)" if PRUNE else " (use PRUNE=1 to remove)"))
    print()
    if kept:
        ink = [k for k in kept if k["kind"] == "ink"]
        blk = [k for k in kept if k["kind"] == "blank"]
        print(f"  ink-rich pairs      : {len(ink)}")
        if ink:
            print(f"    ink columns       : {min(k['ink_columns'] for k in ink)}"
                  f"–{max(k['ink_columns'] for k in ink)}")
            print(f"    depth sd (layers) : "
                  f"{np.mean([k['depth_sd_layers'] for k in ink]):.1f} mean")
            print(f"    distinct depths   : "
                  f"{np.mean([k['depth_levels'] for k in ink]):.1f} mean "
                  f"— TRUE 3D, not projected")
        print(f"  negative-rich pairs : {len(blk)}")
        if blk:
            print(f"    certified blank   : "
                  f"{100*np.mean([k['certified_blank_frac'] for k in blk]):.1f}% mean")
    if dropped:
        print("\n  dropped:")
        for n, f in dropped[:8]:
            print(f"    {n[:52]:52} {f[0]}")
        if len(dropped) > 8:
            print(f"    ... and {len(dropped)-8} more")

    man = dict(issue="ScrollPrize/villa#192", n_pairs=len(kept),
               gate=dict(min_ink_columns=MIN_INK_COLS,
                         min_blank_frac=MIN_BLANK_FRAC,
                         min_depth_sd_layers=MIN_DEPTH_SD,
                         min_depth_levels=MIN_DEPTH_LEVELS),
               note=("Every pair below is measured, not asserted: ink depth is "
                     "verified to VARY across each crop, which is the "
                     "requirement a projected label cannot meet."),
               pairs=kept)
    json.dump(man, open(os.path.join(PAIRS, "MANIFEST.json"), "w"), indent=1)
    print(f"\n-> out/pairs/MANIFEST.json")


if __name__ == "__main__":
    main()
