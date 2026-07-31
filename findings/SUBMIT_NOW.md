# SUBMIT — three clicks, deadline 11:59pm Pacific TONIGHT (July 31)

Discord is **not** the submission mechanism. The official route is the form
below. Do these in order; everything is pre-staged.

---

## 1. Open the pull request (required by the form)

The branch is already pushed. Click this and press "Create pull request":

**https://github.com/ScrollPrize/villa/compare/main...williamshermer-pixel:villa:slice-ink-labels?expand=1**

Title (pre-fill if empty):
```
Add Slice: calibrated 3D ink labels + browser viewer
```

Body:
```
Adds Slice to Community Projects under Ink Detection.

Ready-to-run image/label pairs for ink-detection training, addressing #192
(depth resolved per pixel rather than projected across layers) and #193 (the
generation method). Each pair ships a measured quality certificate — an ink
floor calibrated to a 0.2% false-positive rate on known-blank papyrus, and a
condition-control AUC separating ink from blank sheet of the same
preservation. A QC gate verifies the depth claim rather than asserting it.

Repo: https://github.com/williamshermer-pixel/slice
Viewer: https://slice-site-alpha.vercel.app
```

Copy the PR URL once created — the form asks for it.

---

## 2. Fill the submission form

**https://forms.gle/xoF5C3QsYutKP97x7**

**Email:** williamshermer@gmail.com

**Your full name:** William Shermer

**Team description:**
```
Submitting as an individual.
```

**URL to your open source / publicly available contribution:**
```
https://github.com/williamshermer-pixel/slice
https://slice-site-alpha.vercel.app
https://slice-site-alpha.vercel.app/record
```

**Short description of how your contributions substantially increase the
probability of reading complete scrolls:**
```
Ink labels are a stated bottleneck (villa #192, #193), and #192 names the
specific risk that labels teach a model the underlying surface rather than the
ink. This submission attacks that directly.

1. READY-TO-RUN 3D LABELS (#192). Image/label pairs as plain zarr — image and
label together, 512-cube training tiles, nothing to crop or preprocess. Labels
are 0 unlabelled / 1 ink / 2 certified blank / 3 ink present but depth
ambiguous. Depth is recovered, not projected: the ink model takes a fixed
62-layer input, so we slide that reading window through the stack and give
every pixel a response profile whose peak is its depth, then narrow it using
the crop's own intensity profile (which cannot see ink, but locates the sheet
ink must lie on). Where a profile is flat we label ambiguous rather than
inventing a layer. A QC gate measures that depth actually varies across every
shipped crop and removes pairs that fail — a projected label cannot pass it,
and our own first version was exactly such a projection and was discarded.

2. THE SURFACE-CONFOUND CONTROL (#192's stated fear, measured). Every pair
carries a condition-control AUC: ink separated from blank sheet INSIDE the
text block — same sheet, same preservation, same damage. 0.96–0.99 on curated
segmentations, 0.84 on auto-grown ones. This is how we killed our own false
positives; one earlier candidate scored r=+0.44 held-out and 0.21 on blank
papyrus, i.e. it was reading preservation, not ink.

3. METHOD AND CALIBRATION (#193). Per-scroll depth-band calibration: reading
layers 27-89 instead of the stack centre moved agreement with published calls
from AUC 0.654 to 0.944 on known Scroll 1 letters — the single largest effect
we found, and a failure mode any pipeline using these models can hit.
Per-scribe hand measurement, with a correction that matters: letter heights
taken from connected components of binarized maps are wrong by 3-5x (the
method reads Scroll 1's known 3.00 mm hand as 0.58 mm); a band-FWHM measure
validates at 2.94 mm. Also measured: fine-tuning gains are segmentation-bound
(+0.094 AUC on curated segments vs +0.011 on auto-grown), which says
flattening quality, not model knowledge, is the wall on those scrolls.

4. NEGATIVES, PUBLISHED. Four scrolls searched for uncalled ink with measured
per-letter sensitivity attached, so the silences are interpretable rather than
uninformative. Two of our own previously-announced findings are withdrawn:
spatial-null testing showed 23 of 24 rolled copies of our own maps reproduced
them. Everything is in findings/CALIBRATED_HUNT.md, retractions included.

5. THE VIEWER. Browser-native, no install or login, streaming OME-Zarr
straight from the public bucket client-side: slice-site-alpha.vercel.app —
with the measured ink band marked on the depth control, so the depth finding
above is usable rather than only documented.

Known limits, stated plainly: crops are 1.16 mm square, smaller than one
letter of this scribe's hand — these are training tiles, not readable views.
All pairs are from PHerc0139. Most labelled ink volume is depth-ambiguous
rather than depth-resolved; we would rather withhold a depth than invent one.
And the method requires an existing segmentation, so it does not yet reach
#193's hardest case — labels for regions no segmentation covers. That case is
open and we would like to work on it.
```

**Pull request submission:** paste the PR URL from step 1.

**Terms and Conditions:** Yes, I agree.
(Licence is MIT for code; scroll-data crops keep CC BY-NC with attribution in
`LICENSE-DATA` — both are in the repo.)

---

## 3. Optional but worth it: post in Discord

**https://discord.gg/V4fJhvtaQn** as `willsher` — the post text is in
`findings/SUBMISSION_DRAFT.md` between the `---` marks.

Not the submission mechanism, but their highest-weighted criterion is whether
work gets *used*, and that starts with people seeing it. Worth adding the
honest open question: PHerc0139 segments come back ~30% occupied with no
contiguous column-sized field — is that expected ribbon geometry, or are we
reading the masks wrong?

---

## ADDENDUM (2026-07-31 evening) — cross-energy consensus

Append this to the END of the long "how does this increase the probability of
reading complete scrolls" answer, after the "Known limits" paragraph. Nothing
above changes.

```
ADDED THE SAME DAY — CROSS-ENERGY CONSENSUS (#193, and it upgrades the above).

Three scrolls in the bucket were scanned twice at different photon energies and
published twice with different recipes months apart: PHerc1667, PHerc0139 and
PHerc0814, at 59 keV (the 1.129um-...-L1 flattening) and 78 keV (2.399um). The
two share nothing but the papyrus. That makes a label's confidence measurable
instead of chosen, which is the weakness in every ink label this field ships,
including ours above: they rest on a threshold applied to one model over one
volume, and no measurement says the threshold was right.

Registration is not assumed. After resizing one canvas onto the other by the
voxel ratio the best global fit is sx=1.000 sy=1.000 dy=0 dx=0 -- the two
flattenings share a UV layout -- with residual local warp of median 0 px and
IQR 45 px (0.8 mm), removed with a block phase-correlation field. Registering
on the sheet mask instead is wrong and we report why: the 78 keV flattening
recovers ~1.8x more sheet and drags the fit to a false sy=0.87.

The two scans agree far above chance, and the effect strengthens exactly where
it should. Sweeping the call threshold on one segment, enrichment over a rolled
spatial null goes 4.3x at the top 20% of sheet to 69.3x at the top 1% -- the
strongest ink in each scan is where two independent measurements converge
hardest. Threshold-free Spearman is 0.374. Across all 62 paired segments the
median is 0.456 on PHerc0139, 0.405 on 0814, 0.278 on 1667, every segment at
the p floor of the null.

The uncomfortable half of the same number, which we think the Annotation Team
should have: at a top-decile call the two published maps agree on only about
40% of each other's calls, and allowing a full letter of slack only reaches
56%. Within strongly inked text they trace the same glyphs; the divergence is
concentrated in marginal calls. Any single published map is a weaker ground
truth than it looks.

DELIVERABLE: consensus-certified labels for all 62 paired segments, plain
zarr v2, one raster per segment at 18.064 um/px. 1 = both scans call it,
2 = neither calls it and it clears both the spillover and sheet-edge keep-outs,
3 = exactly one calls it, shipped as its own code rather than silently
resolved. 73.1 cm2 of consensus ink, 215.2 cm2 of certified blank, 138.7 cm2
disputed. Code 2 is the half a threshold cannot give you: "below my cut" is not
"blank", but "neither of two independent scans saw anything, far from anything
either did see" is a measurement. Every array carries its certificate in
.zattrs. Labels only; no scroll image is redistributed.

WE ALSO SEARCHED, AND FOUND NOTHING. Two independent scans average down
independent noise, so a mark too faint for either detector alone can clear a
joint threshold. We searched min(z59, z78) over every letter-sized box on sheet
that both scans cover and neither calls: 128 cm2 on 1667, 108.5 cm2 on 0139.
Nothing survives. On 0139 four segments produced a candidate, best p=0.015,
but across 37 tests you expect ~1.9 at p<=0.05 by chance and nothing clears
Bonferroni. The best-looking candidate reached p=0.019 after 999 nulls and then
died to the render: it sat 0.78 mm from the sheet edge, under half a letter.

That failure found a real flaw and we fixed it rather than dropping the
candidate. Our letter-box accepted any box at least half on sheet, dividing a
partial sum by a shrinking denominator -- and 60.6% of the search area lay
within two letters of a sheet boundary, so the search was dominated by the
region where its own statistic misbehaves. Boxes must now be 95% on shared
sheet and the search is eroded 1.5 letters from every boundary. The 0139
numbers above are post-fix; the earlier ones were contaminated and are marked
as such in findings/CROSSENERGY_1667.md.

Limitation, stated on every certificate: two energies share the papyrus, so
agreement does not separate ink from sheet CONDITION. These labels are
cross-scan certified, not condition-controlled -- the condition-control AUC in
the #192 pairs is the measurement for that axis.
```
