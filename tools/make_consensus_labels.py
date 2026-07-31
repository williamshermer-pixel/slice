#!/usr/bin/env python3
"""Cross-energy consensus ink labels — labels whose confidence is PHYSICAL.

villa #193 asks for methods of generating ink labels. Every label this field
ships, including our own #192 pairs, ultimately rests on a threshold applied to
one model's output over one volume. Choose the threshold differently and the
label changes; there is no measurement that says which choice was right.

Three scrolls in the bucket were scanned TWICE at different photon energies and
published twice with different recipes months apart — PHerc1667, PHerc0139 and
PHerc0814 (59 keV via the 1.129um-...-L1 flattening, and 78 keV via 2.399um).
The two share nothing but the papyrus. That makes a label's confidence
measurable rather than chosen:

    1  CONSENSUS INK    both independent scans call it
    2  CONSENSUS BLANK  neither calls it, and it is far enough from every call
                        and every sheet edge for that silence to mean something
    3  DISPUTED         exactly one scan calls it — shipped as its own code
                        rather than silently resolved in either direction
    0  UNLABELLED       not covered by both scans, or too close to an edge

Code 2 matters as much as code 1. Certified absence is half of supervision and
is the thing a threshold can never give you: "below my cut" is not "blank".

Every array carries a certificate in .zattrs — both source volumes and recipes,
the measured registration, the agreement statistics against a spatial null, the
keep-outs, and the limitation below.

LIMITATION, on every certificate: two energies share the papyrus, so agreement
does not separate ink from sheet CONDITION. Text sits on well-preserved sheet,
and both scans respond to preservation. These labels are cross-scan certified,
NOT condition-controlled. Use the condition-control AUC in the #192 pairs for
that axis.

Labels only. The image half is never redistributed here — the bucket path for
each segment is in the certificate, and the data is CC BY-NC 4.0,
(c) Vesuvius Challenge.

    python3 tools/make_consensus_labels.py            # all three scrolls
    SCROLLS=PHerc0139 python3 tools/make_consensus_labels.py
"""
import glob, json, os, sys, zlib
import numpy as np
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTROOT = os.path.join(ROOT, "out", "consensus")
BUCKET = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"

HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
_DIRS = {"PHerc1667": "s1667"}
DS8_UM = 18.064
KEEPOUT_MM = 1.5            # model spillover past a call, a FIXED distance
EDGE_LETTERS = 1.5          # letter-box must not hang off the sheet
CHUNK = (512, 512)

CODES = {"0": "unlabelled - not covered by both scans, or within the edge "
              "keep-out where a letter-box average is not trustworthy",
         "1": "consensus ink - both independent scans call it",
         "2": "consensus blank - neither scan calls it, and it clears both the "
              "spillover keep-out from any call and the sheet-edge keep-out",
         "3": "disputed - exactly one scan calls it"}


def write_zarr(path, arr, chunks, attrs=None):
    """Minimal zarr v2 writer: zlib-compressed C-order chunks.
    Same writer the #192 pairs use (tools/make_labels_3d.py)."""
    os.makedirs(path, exist_ok=True)
    meta = {"zarr_format": 2, "shape": list(arr.shape),
            "chunks": list(chunks), "dtype": "|u1",
            "compressor": {"id": "zlib", "level": 6},
            "fill_value": 0, "order": "C", "filters": None,
            "dimension_separator": "."}
    open(os.path.join(path, ".zarray"), "w").write(json.dumps(meta))
    if attrs:
        open(os.path.join(path, ".zattrs"), "w").write(json.dumps(attrs, indent=1))
    grid = [int(np.ceil(s / c)) for s, c in zip(arr.shape, chunks)]
    for idx in np.ndindex(*grid):
        sl = tuple(slice(i * c, min((i + 1) * c, s))
                   for i, c, s in zip(idx, chunks, arr.shape))
        block = np.zeros(chunks, np.uint8)
        piece = arr[sl]
        block[tuple(slice(0, p) for p in piece.shape)] = piece
        open(os.path.join(path, ".".join(map(str, idx))), "wb").write(
            zlib.compress(block.tobytes(), 6))
    return int(np.prod(grid))


def sources(pubdir, seg):
    out = {}
    for f in glob.glob(os.path.join(pubdir, f"*-{seg}-*.jpg")):
        b = os.path.basename(f)
        out["59keV" if "1.129um" in b else "78keV"] = b.replace("-ds8.jpg", ".tif")
    return out


def main():
    want = os.environ.get("SCROLLS")
    scrolls = [want] if want else list(HANDS)
    index = []

    for scroll in scrolls:
        base = os.path.join(ROOT, "out", _DIRS.get(scroll, f"xe_{scroll}"))
        xepath = os.path.join(base, "crossenergy.json")
        if not os.path.exists(xepath):
            print(f"{scroll}: no crossenergy.json, skipped")
            continue
        xerep = json.load(open(xepath))["segments"]
        letter_px = HANDS[scroll] * 1000.0 / DS8_UM
        keep_px = int(round(KEEPOUT_MM * 1000.0 / DS8_UM))
        edge_px = EDGE_LETTERS * letter_px

        for f in sorted(glob.glob(os.path.join(base, "xe_*.npz"))):
            seg = os.path.basename(f)[3:-4]
            if seg not in xerep:
                continue
            d = np.load(f)
            m, ca, cb = d["m"], d["ca"], d["cb"]

            lab = np.zeros(m.shape, np.uint8)
            both = ca & cb & m
            one = (ca ^ cb) & m
            lab[one] = 3
            lab[both] = 1

            # certified blank: uncalled, clear of spillover from any call, and
            # clear of the sheet edge
            called = ndimage.uniform_filter((ca | cb).astype(np.float32),
                                            2 * keep_px + 1) > 1e-6
            dist = ndimage.distance_transform_edt(m)
            blank = m & ~called & (dist >= edge_px)
            lab[blank] = 2

            r = xerep[seg]
            n = {k: int((lab == v).sum()) for k, v in
                 (("unlabelled", 0), ("ink", 1), ("blank", 2), ("disputed", 3))}
            tot = int(lab.size)
            attrs = {
                "title": "cross-energy consensus ink labels",
                "scroll": scroll, "segment": seg,
                "codes": CODES,
                "counts_px": n,
                "counts_pct_of_canvas": {k: round(100 * v / tot, 3)
                                         for k, v in n.items()},
                "resolution_um_per_px": DS8_UM,
                "grid": "published ink-map canvas, downsampled 8x (ds8)",
                "letter_height_mm": HANDS[scroll],
                "letter_height_px": round(letter_px, 1),
                "sources": sources(os.path.join(base, "pub"), seg),
                "source_bucket_prefix": f"{BUCKET}/{scroll}/segments/",
                "independence": (
                    "59 keV (1.129um-...-L1 flattening, 2.258 um/voxel) and "
                    "78 keV (2.399um, 2.399 um/voxel): different photon energy, "
                    "reconstruction, flattening run and model recipe, published "
                    "months apart. Shared input: the papyrus only."),
                "registration": (
                    "78 keV map resized onto the 59 keV canvas by the voxel "
                    "ratio; measured best global fit sx=1.000 sy=1.000 dy=0 "
                    "dx=0 (the flattenings share a UV layout), then a block "
                    "phase-correlation field for residual warp, median 0 px, "
                    "IQR ~45 px (0.8 mm). Registering on the sheet MASK is "
                    "wrong -- 78 keV recovers ~1.8x more sheet and drags the "
                    "fit to a false sy=0.87."),
                "agreement": {
                    "shared_sheet_pct": r["shared_sheet_pct"],
                    "letterscale_spearman_r": r["r_letterscale"],
                    "jaccard": r["jaccard"],
                    "jaccard_spatial_null": r["null_mean"],
                    "enrichment_over_null": r["enrichment"],
                    "p_vs_rolled_null": r["p"],
                    "call_threshold": "each scan's own top decile, letter-box "
                                      "integrated (per-pixel thresholding "
                                      "recovers only 10-12% of known letters)"},
                "keepouts": {"spillover_mm": KEEPOUT_MM,
                             "sheet_edge_letters": EDGE_LETTERS,
                             "why": "spillover is the model blend kernel and is "
                                    "a fixed physical distance, not a multiple "
                                    "of the hand; the edge keep-out exists "
                                    "because 60.6% of an unrestricted search "
                                    "area lies within two letters of a sheet "
                                    "boundary, where a letter-box average runs "
                                    "off the sheet and manufactured this "
                                    "project's first cross-energy candidate"},
                "LIMITATION": (
                    "Two energies share the papyrus, so agreement does NOT "
                    "separate ink from sheet CONDITION -- text sits on "
                    "well-preserved sheet and both scans respond to "
                    "preservation. These labels are cross-scan certified, not "
                    "condition-controlled."),
                "license": "CC BY-NC 4.0, (c) Vesuvius Challenge. Derived from "
                           "published ink detections. Labels only -- no scroll "
                           "image data is redistributed here.",
                "generator": "tools/make_consensus_labels.py",
            }
            path = os.path.join(OUTROOT, scroll, f"{seg}.zarr")
            write_zarr(path, lab, CHUNK, attrs)
            index.append(dict(scroll=scroll, segment=seg,
                              shape=list(lab.shape), **n))
            print(f"{scroll} {seg}  ink {n['ink']:>9,}  blank {n['blank']:>10,}  "
                  f"disputed {n['disputed']:>9,}")

    os.makedirs(OUTROOT, exist_ok=True)
    with open(os.path.join(OUTROOT, "index.json"), "w") as f:
        json.dump(dict(codes=CODES, um_per_px=DS8_UM, segments=index), f, indent=1)
    ink = sum(x["ink"] for x in index)
    blank = sum(x["blank"] for x in index)
    disp = sum(x["disputed"] for x in index)
    px_mm2 = (DS8_UM / 1000) ** 2
    print(f"\n{len(index)} segments -> {OUTROOT}")
    print(f"  consensus ink    {ink:>12,} px = {ink*px_mm2/100:8.1f} cm2")
    print(f"  consensus blank  {blank:>12,} px = {blank*px_mm2/100:8.1f} cm2")
    print(f"  disputed         {disp:>12,} px = {disp*px_mm2/100:8.1f} cm2")


if __name__ == "__main__":
    main()
