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

**The deliverable (issue #192):** machine-generated ink labels with quality
certificates, as plain zarr v2 (zlib — any zarr client reads them). Per
window: `label/` uint8 (D×4096×4096) on the surface volume's own grid —
1 = ink at a calibrated floor, 2 = certified-blank negative — plus `conf/`
(the raw probability) and `.zattrs` carrying full provenance: source volume,
window, depth band, floor + measured blank FPR (0.2%), and the
condition-control AUC. Generator + pair-fetcher in the repo
(`tools/make_labels_3d.py`, `tools/fetch_pair.py` — the scroll data itself
is never redistributed). ~180 windows across 4 scrolls to start.

Three properties aimed at #192's stated concerns:

**1. "Only the detectable ink patterns" — measured, not assumed.** The
label floor is set on known-blank papyrus at 0.2% false-positive rate, and
every scroll's labels ship with a CONDITION CONTROL: the detector's AUC
separating known ink from blank sheet *inside the text block* — same sheet,
same preservation, same damage. That is the direct test for "the model
learned surface, not ink" (it is also how our own earlier false positives
died: one candidate scored r=+0.44 held-out and 0.21 on blank papyrus —
it was detecting preservation). Measured: 0.96–0.99 on curated
segmentations (PHerc0139, Scroll 1), 0.84 on auto-grown ones.

**2. Depth-true where measured, and honest where not.** Labels are nonzero
only in the measured ink band (z27..z89 of the 116-layer stacks) — reading
a blindly-centred band instead scores AUC 0.654 vs 0.944 with the measured
band, the single largest effect we found (check your pipeline for this
one). Voxel-level depth attribution is NOT claimed, and the .zattrs say so.

**3. Certified negatives.** Training pairs need certified absence:
label==2 marks blank sheet ≥1.5 mm from any published call (outside
measured model spillover) and below the floor.

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
