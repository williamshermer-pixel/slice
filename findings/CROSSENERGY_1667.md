# Cross-energy consensus on PHerc1667 — an artifact filter that is physical

*2026-07-31. Tools: `tools/crossenergy_1667.py`, `tools/conjunction_1667.py`,
`tools/render_crossenergy.py`. Data: `out/s1667/crossenergy.json`,
`conjunction.json`. Renders: `out/s1667/evidence_xe_<segment>.png`.*

## Why this scroll, and why now

PHerc1667 was the best unsearched ground left in the library and the handoff
undersold it. All seven of its segments are **curated** (`flatboi`, not
auto-grown) — and curation is the thing that decides whether anything works
here: fine-tune gains measured +0.094 AUC on curated segments against +0.011
on auto-grown ones. Its hand is 1.63 mm (band-FWHM, `tools/measure_hand.py`).
The field read it end-to-end in June 2026, so a positive control exists. And
it had never been differential-searched.

The fact that changes the method: **every 1667 segment was scanned twice and
published twice.**

| | 59 keV | 78 keV |
| --- | --- | --- |
| surface volume | `1.129um-…-L1`, 2.258 µm/voxel, 116 layers | `2.399um-…`, 2.399 µm/voxel, 109 layers |
| ink map recipe | `mrg20736-1um-s1z2` | `new_canon_autoresearch_recipe` |
| published | 2026-07-09 | 2026-04-17 |

Different photon energy, different reconstruction, different flattening run,
different model recipe, three months apart.

**How independent, exactly.** The *scans* are independent in physics — energy,
reconstruction, flattening. The two ink *maps* are both ScrollPrize model
output, and nothing in the public bucket says whether the two recipes share
architecture, training data or lineage. If they do, part of the agreement
measured below is shared MODEL bias rather than shared ink. The accurate label
for this method is **cross-energy and cross-recipe, not fully independent** —
the physics half of the independence is verified, the model half is not. What
would settle it: a detector of different lineage as a third opinion, or a word
from the maintainers. We are asking.

That matters because of how this project's candidates have died. The
2026-07-29 differential died when 23 of 24 rolled copies of *our own map*
reproduced it. The aimed-window family died as box-filter edge geometry after
clearing spatial nulls, independent replication *and* a physics control. Both
survived everything because every check drew on the same input volume. **Two
energies do not share an input volume.** Agreement between them is evidence no
null computed over a single map can supply — bounded by the lineage caveat
above.

## Registration — measured, not assumed

The two canvases differ by exactly the voxel ratio. After resizing the 78 keV
map onto the 59 keV canvas, the best global fit over a scale-and-shift search
on letter-scale high-passed text is **sx=1.000, sy=1.000, dy=0, dx=0** — the
two flattenings share a UV layout. Residual local warp is small: block phase
correlation gives median displacement 0 px with an IQR of ~45 px (0.8 mm), and
69% of sharp blocks sit within ±32 px. A block field takes it out.

Two ways to get this wrong, both hit on the way here:

- **Registering on the sheet mask is wrong.** The 78 keV flattening recovers
  ~1.8× more sheet area, so mask overlap drags the fit to a false sy=0.87.
  Register on text, not on outline.
- **Cropping each map to its own content bbox is wrong** — it destroys the very
  alignment the shared UV layout gives you for free.

Everything below is computed on the published ds8 maps: **18.064 µm/px**, so a
1.63 mm letter spans **~90 px**. Calls integrate over a letter-sized box, never
per-pixel — per-pixel thresholding recovers 10–12% of known letters, letter-box
integration 78–98%.

## Result 1 — the two scans agree far above chance, and disagree a lot

Agreement is not an artifact of where the call threshold is put. Sweeping it on
segment `20240304141531` (Jaccard of the two call masks against a rolled-map
null):

| top % of sheet called | both | Jaccard | null | enrichment |
| --- | --- | --- | --- | --- |
| 20% | 9.29% | 0.303 | 0.070 | 4.3× |
| 10% | 3.97% | 0.247 | 0.036 | 6.8× |
| 5% | 1.65% | 0.198 | 0.016 | 12.1× |
| 3% | 0.87% | 0.169 | 0.007 | 25.0× |
| 1% | 0.23% | 0.131 | 0.002 | **69.3×** |

Enrichment rises monotonically as the call tightens. That is the signature of
real shared signal: the strongest ink in each scan is exactly where two
independent measurements converge hardest. The threshold-free check agrees —
Spearman ρ = 0.374 on letter-box, high-passed values over shared sheet.

The other half of the same number is less comfortable and worth saying plainly:
at a top-decile call the two published maps **agree on only ~40% of each
other's calls**. Two independent detectors on the same sheet disagree about the
majority of what each reports. Any single published map is a weaker ground
truth than it looks.

All seven 1667 segments, top-decile calls, against a 24-roll spatial null — every
one at p = 0.040, which is the floor for 24 nulls:

| segment | shared | ρ | consensus | Jaccard | null | enrichment |
| --- | --- | --- | --- | --- | --- | --- |
| 20240304141531 | 52.5% | +0.223 | 3.97% | 0.247 | 0.031 | 7.9× |
| 20240304144031 | 50.4% | +0.405 | 5.45% | 0.374 | 0.021 | **17.9×** |
| 20240304161941 | 46.7% | +0.278 | 4.34% | 0.277 | 0.032 | 8.7× |
| 20251206103305 | 51.6% | +0.153 | 4.44% | 0.286 | 0.018 | 15.5× |
| 20251208130119 | 47.2% | +0.231 | 3.83% | 0.237 | 0.023 | 10.5× |
| 20251212185248 | 45.0% | +0.315 | 4.37% | 0.279 | 0.019 | 14.5× |
| 20251220020000 | 43.7% | +0.296 | 4.35% | 0.278 | 0.030 | 9.4× |

**PHerc0139 agrees far more strongly** — 37 paired segments, median ρ **0.456**,
median enrichment **25.1×**, best 89.4×, all at p = 0.040. That is the curated,
calibrated scroll behaving as curation predicts.

The disagreement is not merely stroke-level registration. Allowing a full letter
of slack on segment 20240304144031, Jaccard goes 0.374 → 0.561: within strongly
inked text the two scans trace the same glyphs (see the render — the Greek is
unmistakable), but **~44% of calls still disagree at one-letter tolerance**. The
divergence is concentrated in the marginal calls and it is real.

## The method generalises — and where it does not

Surveyed against the live bucket, 2026-07-31. A scan only counts if it samples a
15 µm ink layer at 3+ voxels, so the 9.362 µm / 8.64 µm / 45 µm volumes are
excluded on physics:

| scroll | pair | segments |
| --- | --- | --- |
| PHerc1667 | 59 keV + 78 keV | 7 of 7, curated |
| PHerc0139 | 59 keV + 78 keV | **37 of 38** |
| PHerc0814 | 59 keV + 78 keV | 19 |
| PHerc0343P | one usable scan | — |
| PHerc0500P2 | one usable scan | — |
| PHercParis4 | two scans, both 78 keV | not energy-independent |
| PHerc0172 | no ink-detection maps | the physics control |

## Result 2 — the conjunction search

Two independent measurements do not only cross-check; they average down
independent noise. A mark too faint to clear either detector's threshold alone
can clear a joint one, because the noise is independent and the ink is not.
This is the only route this project has found to ink that neither published map
reports, with no GPU and no new model.

Statistic: **min(z₅₉, z₇₈)** over a letter-sized box, computed only on sheet
that both scans cover and neither calls, with a fixed 1.5 mm keep-out from any
call (the blend kernel smears past a letter's called extent; a keep-out
proportional to the hand would be the wrong shape). `min` rather than `sum` on
purpose — a sum lets one scan's artifact carry a spot alone, which is the exact
failure this design exists to prevent.

Null: roll one scan's z-map by ≥3 letters. Preserves each map's histogram and
autocorrelation, destroys their mutual registration.

### What this design cannot rule out

**Sheet condition.** Text sits on well-preserved papyrus, so preservation
correlates with "text here", and both energies respond to it — a shared cause,
not independent noise. Rolling one map destroys registration but not condition,
so the null above does **not** separate ink from condition. Two things push
back and neither is conclusive: the letter-scale high-pass removes smooth
preservation gradients, and real text lies in rows at a fixed pitch while
condition does not. The render is the arbiter. Anything surviving here is a
**candidate, not a reading.**

### Result: the search is quiet, on all three scrolls

**PHerc1667 — nothing.** Zero survivors on all seven segments, ~128 cm² of sheet
that neither published detector calls. The line filter agrees: every segment
p ≥ 0.18.

**PHerc0139 — nothing that survives.** 108.5 cm² searched across 37 segments
after the edge correction below. Four segments produced a survivor, best
p = 0.015. Across 37 tests you expect ~1.9 at p ≤ 0.05 by chance and we have 3;
Poisson P(≥3) = 0.28. Nothing clears Bonferroni (0.05/37 = 0.00135). Consistent
with noise.

The one candidate that looked real is worth recording, because of how it died.
On 20260317000000 it reached p = 0.019 after 999 nulls — and the render put it
**0.78 mm from the sheet edge, under half a letter.** Not ink. Geometry.

### The check that was missing

That candidate exposed a flaw in the instrument, not just in itself. The
letter-box mean accepted any box at least half on sheet (`den > 0.5`), dividing a
partial sum by a shrinking denominator — unstable exactly at a boundary. Worse:
**60.6% of the search area lay within two letters of a sheet edge**, so the
search was majority-dominated by the region where its own statistic misbehaves.

Fixed: a letter-box must now be ≥95% on shared sheet, and the search is eroded
1.5 letters back from every sheet boundary — a fixed physical distance, the same
reasoning as the spillover keep-out. Re-running 0139 under the corrected
instrument is what produced the numbers above. Every cross-energy figure
reported before that fix was computed on the contaminated region.

## Not a #192 deliverable — a QC overlay, and a certificate

**Read #192 before reading this section.** It asks for ink labels "in true 3d
rather than a single image projected across multiple layers." The rasters below
are **2D**, one flat image per segment at ds8 (18.064 µm/px). They are exactly
the projection the issue forbids, and calling them a #192 deliverable would be
shipping the mistake this project already threw away once. They were built as
one here on 2026-07-31 and demoted before submission.

What they legitimately are: **a QC overlay for annotators** — a map of where two
scans at different energies agree, disagree, or are both silent. #192's first
line says current ink labels are drawn by a human annotator over model output;
a "the second scan does not corroborate this call" overlay is directly useful to
that person.

The part that does attach to #192 is `tools/certify_pairs_crossenergy.py`, which
annotates the true-3D pairs (`[116, 512, 512]`, native resolution, ready-to-run)
with a corroboration block in each label's `.zattrs`. It found two suspect pairs
inside our own shipped deliverable: one ink pair corroborated 0.00 by the second
scan, and one "certified blank" pair that the second scan reads as 94.5% inked.
Both are flagged in place rather than dropped.

Nor does any of this answer **#193's actual problem**, which is the catch-22 of
needing labels for regions that have no segmentation. This method requires a
flattened surface volume and two published ink maps — it lives inside that
catch-22.

### The QC overlay itself

`tools/make_consensus_labels.py` → `out/consensus/<scroll>/<segment>.zarr`,
plain zarr v2 / zlib, one uint8 raster per segment at 18.064 µm/px:

| code | meaning |
| --- | --- |
| 1 | **consensus ink** — both scans (59 keV and 78 keV) call it |
| 2 | **consensus blank** — neither calls it, clear of both the spillover and sheet-edge keep-outs |
| 3 | **disputed** — exactly one scan calls it, shipped as its own code rather than silently resolved |
| 0 | unlabelled — not covered by both scans, or inside the edge keep-out |

Code 2 is the half that thresholds cannot give you: "below my cut" is not
"blank", but "neither of two scans at different energies saw anything here, and it is far
from anything either did see" is a measurement. Code 3 is shipped rather than
resolved because resolving it would be exactly the arbitrary choice this method
exists to avoid.

Every array carries a certificate in `.zattrs`: both source volumes and recipes,
the measured registration, agreement against the spatial null, the keep-outs and
why they are what they are, and the limitation above. Labels only — no scroll
image is redistributed; the bucket path for the image half is in the
certificate. Verified end-to-end: reassembling all chunks reproduces the
certificate counts exactly.

## What this is worth, stated against what the issues actually ask

Written after re-reading #192 and #193 in full, which should have happened
before any of this was built.

**It does not close either issue.** #192 wants true-3D ready-to-run ink labels;
the rasters here are 2D. #193 wants label generation that escapes the
segmentation catch-22; this method requires a segmentation. Anyone reading it
as an answer to either has been misled, so the sections above say so plainly.

**What it does contribute, honestly scoped:**

1. **A corroboration test for any existing ink label** — does a scan at a
   different photon energy, through a different reconstruction and recipe,
   agree? Applied to our own #192 pairs it found one ink pair corroborated 0.00
   and one "certified blank" that the second scan reads as 94.5% inked. A
   submission that audits itself and ships the failures is worth more than one
   that does not.
2. **A number the annotation team does not have** — two published maps of the
   same sheet agree on ~40% of each other's calls, 56% at one-letter tolerance.
   That bounds how far any single map can serve as ground truth, which matters
   directly to #192's opening complaint about annotators drawing over model
   output.
3. **A QC overlay** for those annotators, for all 62 paired segments.
4. **A powered negative**: ~237 cm² of uncalled sheet searched with a method
   that gains sensitivity from scan independence, and found nothing — with the
   sensitivity stated rather than implied.

**The bound on all four:** both recipes are ScrollPrize models whose shared
lineage cannot be verified from the public bucket. This is cross-energy and
cross-recipe, not fully independent, and every certificate says so.

