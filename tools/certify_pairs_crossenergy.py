#!/usr/bin/env python3
"""Attach a cross-energy corroboration certificate to the true-3D #192 pairs.

READ #192 BEFORE CHANGING THIS. It asks for ink labels "in true 3d rather than
a single image projected across multiple layers", ready-to-run. The pairs in
out/pairs are that: [116, 512, 512], full depth stack, native canvas
resolution, no preprocessing. This tool does NOT produce labels and must never
replace them — it annotates them.

(The cross-energy consensus rasters in out/consensus are 2D at ds8. They are a
QC overlay for annotators, NOT a #192 deliverable, and calling them one would
be shipping exactly the projection the issue forbids. That mistake was made
here on 2026-07-31 and caught before submission.)

What this adds. #192's stated fear is labels that teach a model "the underlying
surface rather than the ink itself". Three of the scrolls were scanned at two
photon energies and published with two different ink recipes, so for any label
we can ask a question no single map can answer: does a second scan, at a
different energy and through a different reconstruction, corroborate this call?

Per pair we write a `cross_energy` block into the label's .zattrs:

    footprint_px            the label's ink footprint collapsed to (y, x)
    corroborated_frac       fraction of that footprint the 78 keV scan also calls
    single_scan_frac        fraction only the 59 keV scan calls
    local_agreement         Jaccard of the two scans' calls in this crop
    segment_agreement       the same measured over the whole segment, for context
    verdict                 corroborated / mixed / single-scan-only

A blank pair gets the mirror question: does the second scan agree it is blank?
A "certified blank" both scans call empty is worth more than one model's silence.

Bounds, stated in the block itself: the corroboration is sampled from the ds8
published maps (18.064 um/px) upsampled to canvas coordinates, so it is a
letter-scale check, not voxel-scale. It carries no depth — it answers "is there
ink at this (y,x)", not "at this layer". And the two recipes are both ScrollPrize
models of unverified lineage, so agreement bounds confidence from above.

    python3 tools/certify_pairs_crossenergy.py            # writes into out/pairs
    DRY=1 python3 tools/certify_pairs_crossenergy.py      # report only
"""
import glob, json, os, re, sys, zlib
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = os.path.join(ROOT, "out", "pairs")
DS8 = 8                      # published map ds8 vs canvas
DRY = bool(os.environ.get("DRY"))
_DIRS = {"PHerc1667": "s1667"}

# segment suffixes contain underscores ("-w025_2025010863"), so the tail before
# the "__kind__" delimiter must be non-greedy any-char, not [^_]*
NAME = re.compile(r"^(?P<seg>\d{14}).*?__(?P<kind>ink|blank)__y(?P<y>\d+)_x(?P<x>\d+)$")


def read_zarr(path):
    z = json.load(open(os.path.join(path, ".zarray")))
    ch, sh = z["chunks"], z["shape"]
    grid = [-(-s // c) for s, c in zip(sh, ch)]
    a = np.zeros(sh, np.uint8)
    for idx in np.ndindex(*grid):
        f = os.path.join(path, ".".join(map(str, idx)))
        if not os.path.exists(f):
            continue
        b = np.frombuffer(zlib.decompress(open(f, "rb").read()),
                          np.uint8).reshape(ch)
        sl = tuple(slice(i * c, min((i + 1) * c, s))
                   for i, c, s in zip(idx, ch, sh))
        a[sl] = b[tuple(slice(0, x.stop - x.start) for x in sl)]
    return a


def main():
    out = []
    cache = {}
    for scroll_dir in sorted(glob.glob(os.path.join(PAIRS, "PHerc*"))):
        scroll = os.path.basename(scroll_dir)
        base = os.path.join(ROOT, "out", _DIRS.get(scroll, f"xe_{scroll}"))
        xepath = os.path.join(base, "crossenergy.json")
        if not os.path.exists(xepath):
            print(f"{scroll}: no cross-energy data, skipped")
            continue
        xerep = json.load(open(xepath))["segments"]

        for pdir in sorted(glob.glob(os.path.join(scroll_dir, "*"))):
            m = NAME.match(os.path.basename(pdir))
            if not m:
                continue
            seg, kind = m["seg"], m["kind"]
            y0, x0 = int(m["y"]), int(m["x"])
            if seg not in xerep:
                out.append(dict(pair=os.path.basename(pdir), seg=seg,
                                status="no cross-energy for this segment"))
                continue
            if seg not in cache:
                d = np.load(os.path.join(base, f"xe_{seg}.npz"))
                cache[seg] = (d["ca"], d["cb"], d["m"])
            ca, cb, sheet = cache[seg]

            lab = read_zarr(os.path.join(pdir, "label"))
            # 1 = ink in the #192 code set; collapse depth to a (y,x) footprint
            foot = (lab == 1).any(axis=0)
            H, W = foot.shape

            if y0 % DS8 or x0 % DS8:
                out.append(dict(pair=os.path.basename(pdir), seg=seg,
                                status=f"crop origin not ds8-aligned "
                                       f"({y0 % DS8},{x0 % DS8}) -- skipped "
                                       f"rather than silently misaligned"))
                continue
            ys, xs = y0 // DS8, x0 // DS8
            yh, xw = -(-H // DS8), -(-W // DS8)
            if ys + yh > ca.shape[0] or xs + xw > ca.shape[1]:
                out.append(dict(pair=os.path.basename(pdir), seg=seg,
                                status="crop outside the ds8 map"))
                continue
            A = ca[ys:ys + yh, xs:xs + xw]
            B = cb[ys:ys + yh, xs:xs + xw]
            S = sheet[ys:ys + yh, xs:xs + xw]
            # footprint downsampled to ds8 the same way
            F = foot[:yh * DS8, :xw * DS8]
            F = np.pad(F, ((0, yh * DS8 - F.shape[0]), (0, xw * DS8 - F.shape[1])))
            F = F.reshape(yh, DS8, xw, DS8).any(axis=(1, 3))

            r = xerep[seg]
            blk = {
                "question": "does a second scan at a different photon energy "
                            "corroborate this label?",
                "scans": {"59keV": "1.129um-...-L1 flattening, recipe "
                                   "mrg20736-1um-s1z2",
                          "78keV": "2.399um flattening, recipe "
                                   "new_canon_autoresearch_recipe"},
                "segment_agreement": {
                    "jaccard": r["jaccard"], "null": r["null_mean"],
                    "enrichment": r["enrichment"], "p": r["p"],
                    # Pearson on letter-scale high-passed pixels. It was once
                    # labelled "spearman" here; it never was one.
                    "highpass_pearson_r": r["r_letterscale"]},
                "BOUNDS": (
                    "Sampled from the ds8 published maps (18.064 um/px) in "
                    "canvas coordinates: a LETTER-SCALE check, not voxel-scale, "
                    "and it carries NO depth -- it answers 'is there ink at this "
                    "(y,x)', not 'at this layer'. The label's depth claim is "
                    "unaffected and rests on the sliding-window profile. Both "
                    "recipes are ScrollPrize models of unverified lineage, so "
                    "agreement bounds confidence from above, not below."),
            }

            # BOTH maps, always. The first version of this tool read only the
            # 78 keV map and misdiagnosed both of its headline findings: an ink
            # pair scored "single-scan-only" that NEITHER scan calls (a label/
            # derivation question, nothing to do with cross-energy), and a
            # blank pair blamed on "the second scan" when 89.9% of it is called
            # by BOTH scans. A verdict that cannot see the home map cannot say
            # who disagrees with whom.
            if kind == "ink":
                n = int(F.sum())
                if n == 0:
                    blk.update(verdict="no ink footprint in this crop")
                else:
                    home = float((F & A).sum() / n)     # 59 keV, the source
                    other = float((F & B).sum() / n)    # 78 keV, independent
                    blk.update(
                        footprint_px_ds8=n,
                        called_by_source_59kev_frac=round(home, 3),
                        corroborated_by_78kev_frac=round(other, 3))
                    if home < 0.2:
                        blk.update(verdict=(
                            "not called by its own source map at ds8 -- a "
                            "label-derivation question, not a cross-energy "
                            "one; the second scan cannot corroborate or "
                            "dispute what the first never called"))
                    else:
                        blk.update(verdict=(
                            "corroborated" if other >= 0.5 else
                            "mixed" if other >= 0.2 else
                            "not corroborated by the 78 keV scan"))
            else:
                inside = S & ~F
                n = int(inside.sum())
                if n == 0:
                    blk.update(verdict="no shared sheet in this crop")
                else:
                    both = float((inside & A & B).sum() / n)
                    only_a = float((inside & A & ~B).sum() / n)
                    only_b = float((inside & B & ~A).sum() / n)
                    quiet = float((inside & ~A & ~B).sum() / n)
                    blk.update(
                        sheet_px_ds8=n,
                        both_scans_blank_frac=round(quiet, 3),
                        called_by_both_frac=round(both, 3),
                        called_59kev_only_frac=round(only_a, 3),
                        called_78kev_only_frac=round(only_b, 3))
                    if quiet >= 0.9:
                        blk.update(verdict="both scans agree blank")
                    elif both >= 0.5:
                        blk.update(verdict=(
                            "BOTH scans call ink over most of this crop -- "
                            "the blank label is contradicted by both maps, "
                            "not disputed between them"))
                    else:
                        blk.update(verdict="partially disputed")

            lp = os.path.join(pdir, "label", ".zattrs")
            att = json.load(open(lp)) if os.path.exists(lp) else {}
            att["cross_energy"] = blk
            if not DRY:
                json.dump(att, open(lp, "w"), indent=1)
            out.append(dict(pair=os.path.basename(pdir), seg=seg, kind=kind,
                            **{k: v for k, v in blk.items()
                               if k in ("verdict",
                                        "called_by_source_59kev_frac",
                                        "corroborated_by_78kev_frac",
                                        "both_scans_blank_frac",
                                        "called_by_both_frac")}))
            print(f"{kind:5s} {os.path.basename(pdir)[:52]:54s} "
                  f"{blk.get('corroborated_by_78kev_frac', blk.get('both_scans_blank_frac','-'))}"
                  f"  {blk['verdict'][:60]}")

    p = os.path.join(PAIRS, "CROSSENERGY_CERTIFICATE.json")
    if not DRY:
        json.dump(dict(note="cross-energy corroboration attached to the true-3D "
                            "#192 pairs; this is a certificate, not a label set",
                       pairs=out), open(p, "w"), indent=1)
    ink = [o for o in out if o.get("kind") == "ink"
           and "corroborated_by_78kev_frac" in o]
    bl = [o for o in out if o.get("kind") == "blank" and "both_scans_blank_frac" in o]
    if ink:
        v = [o["corroborated_by_78kev_frac"] for o in ink]
        print(f"\nink pairs   n={len(ink)}  corroborated frac "
              f"min {min(v):.2f} median {sorted(v)[len(v)//2]:.2f} max {max(v):.2f}")
    if bl:
        v = [o["both_scans_blank_frac"] for o in bl]
        print(f"blank pairs n={len(bl)}  both-scans-blank frac "
              f"min {min(v):.2f} median {sorted(v)[len(v)//2]:.2f} max {max(v):.2f}")
    print(("DRY RUN, nothing written" if DRY else f"wrote {p}"))


if __name__ == "__main__":
    main()
