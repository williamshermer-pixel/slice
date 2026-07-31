# Progress Prize submission — DRAFT v3 (2026-07-30)

For William to review. Deadline July 31, 11:59pm Pacific. v3 supersedes v2:
the submission now answers the wishlist directly — only three `help wanted`
issues are open, and two of them (#192 accurate 3d ink labels, #193 label
generation methods) are exactly what this campaign built. Everything claimed
is measured and reproducible from the repo; nothing is a reading.

## To file

1. `gh repo edit williamshermer-pixel/slice --visibility public`
2. Confirm LICENSE is MIT; README points at findings/CALIBRATED_HUNT.md
3. Post in the Vesuvius Discord as `willsher`

## The Discord post

---

**Calibrated 3D ink labels + the method (re: villa #192/#193) — plus a
browser viewer, a depth-band bug you may also have, and four scrolls of
honestly-calibrated negatives**

**The deliverable (issue #192):** ready-to-run image/label pairs as plain
zarr v2 — `image/` and `label/` together in one directory, 512³ crops, nothing
to crop or preprocess. Labels are `0` unlabelled / `1` ink / `2` certified
blank / `3` ink present but depth ambiguous. Generator, QC gate and samples in
the repo (`tools/make_pairs.py`, `tools/verify_pairs.py`, `samples/pairs/`).

Three properties aimed at what the issue actually asks:

**1. The depth is recovered, not projected.** Your model is fixed at 62 input
layers and emits a flat 2D map, so we slide that reading window through the
stack (offsets 0,14,27,41,54) and give every pixel a response profile — its
peak is the ink's depth. Then we intersect that with the crop's own intensity
profile, which locates the *sheet* per pixel (intensity can't see ink —
density contrast r≈0.002 — but it sees papyrus, and ink lies on papyrus),
narrowing attribution to ±5 layers. Where a profile is flat we label
**ambiguous** rather than guess. `verify_pairs.py` then measures that depth
varies across every shipped crop — mean sd 4 layers over ~9 distinct depth
centres. A single image projected across layers cannot pass that gate. Our own
first attempt was exactly that projection and was thrown away.

**2. "Only the detectable ink patterns" is measured.** Positives clear a floor
calibrated on known-blank papyrus at a **0.2% false-positive rate**, and every
pair carries a **condition-control AUC**: ink separated from blank sheet
*inside* the text block — same sheet, same preservation, same damage. That is
the direct test for the risk you name in the issue, models learning the
surface instead of the ink. Measured 0.96–0.99 on curated segmentations, 0.84
on auto-grown ones. It is also how our own earlier false positives died: one
candidate scored r=+0.44 held-out and 0.21 on blank papyrus — it was reading
preservation.

**3. Empty pairs are removed, not counted.** The QC gate drops any crop
without real supervision; half the first batch failed it. The manifest carries
per-pair statistics so the set can be audited rather than trusted.

**The method (issue #193)** is the campaign behind the labels, all in the
repo: per-scroll depth-band calibration; per-scribe hand measurement
(band-FWHM, validated 2.94 mm vs Scroll 1's known 3.00 — component-based
measures read 0.58 mm and are wrong 3–5×); letter-scale detection with
statistical power (78–98% per-letter on curated segmentations); mandatory
spatial-null validation (we withdrew two of our own announced findings when
23/24 rolled copies of our own maps reproduced them — the negatives and the
retractions are published, `findings/CALIBRATED_HUNT.md`); and one
label-quality result for segmentation planning: **fine-tune gains are
segmentation-bound** (+0.094 AUC from per-scribe fine-tuning on curated
segments vs +0.011 on auto-grown ones — flattening quality, not model
knowledge, is the wall).

**The tool:** https://slice-site-alpha.vercel.app — no download, no login.
Streams OME-Zarr straight from the public bucket, client-side only.
Shareable URL coordinates, surface-volume depth scrubbing, ink labelling
with mask export. The method and every number above, with figures:
https://slice-site-alpha.vercel.app/record

Feedback wanted: which segments/windows would be most useful labelled next —
the generator runs anywhere at ~1 GPU-min per window.

---

## Notes for William

- Lead is the LABELS because that is the literal wishlist ask ("good first
  issue" tag on #192, format matched, certificates attached). The viewer and
  the findings ride behind it.
- No overclaims: no letters read, negatives stated as negatives, retractions
  named. The credibility of "too weak to call" is the asset.
- If asked "are these labels better than the manual ones": answer honestly —
  they are DIFFERENT: machine-generated at a stated FPR with a
  surface-confound control, cheap at scale; manual labels encode human letter
  knowledge these don't. Complementary, and #192 explicitly worries about the
  manual failure mode these measure.
