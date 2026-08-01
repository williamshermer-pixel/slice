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

## ADDENDUM (2026-07-31 evening) — a diagnostic, not a label set

Append to the END of the long "how does this increase the probability of
reading complete scrolls" answer, after the "Known limits" paragraph.

Framing note (do not paste this bit): this is aimed at the 2026 Open Problems
page, not at #192/#193 as a labels deliverable. That page's "What's next?" asks
"can we reduce the dependence on approximate labels, and reliably tell 'no ink'
apart from 'no ink recovered yet'?", its bottleneck table asks for "stronger
diagnostics", and its label-quality section asks for active learning that
"identifies the most uncertain or valuable regions and asks humans to correct
only those." That is what this is.

```
ADDED THE SAME DAY — A DIAGNOSTIC FOR "NO INK" VS "NO INK RECOVERED YET".

Your Open Problems page asks whether we can reliably tell "no ink" from "no ink
recovered yet", and lists stronger diagnostics as what would help most with
cross-scroll generalization. This is an attempt at one, plus the uncertainty
ranking your label-quality section asks for.

THE LEVER. Three scrolls were scanned at two photon energies and published with
two different ink recipes: PHerc1667, PHerc0139 and PHerc0814, at 59 keV (the
1.129um-...-L1 flattening, recipe mrg20736-1um-s1z2) and 78 keV (2.399um,
new_canon_autoresearch_recipe). For any ink label we can therefore ask: does a
second scan corroborate this? We could not find that comparison published
anywhere, and it is free -- both maps are already in the bucket for 62
segments.

Registration is measured, not assumed. Resizing one canvas onto the other by
the voxel ratio, the best global fit is sx=1.000 sy=1.000 dy=0 dx=0 -- the two
flattenings share a UV layout -- with residual warp median 0 px, IQR 45 px
(0.8 mm), removed by a block phase-correlation field. Registering on the sheet
mask is wrong: the 78 keV flattening recovers ~1.8x more sheet and drags the
fit to a false sy=0.87.

WHAT IT SAYS. Agreement is far above chance and strengthens as the call
tightens -- 4.3x over a rolled spatial null at the top 20% of sheet, 69.3x at
the top 1%, threshold-free Spearman 0.374, median 0.456 across 37 PHerc0139
segments, every segment at the null's p floor. But at a top-decile call the two
maps agree on only ~40% of each other's calls, and 56% allowing a full letter
of slack.

We are careful about what that disagreement means, because your own page says
1.1 um data yields cleaner results than 2.4 um. The two maps are therefore not
peers, and part of the divergence is that known resolution asymmetry rather
than either being wrong. What the number does bound is how far a single
published map can serve as ground truth for the annotator who is, per #192,
drawing letters over model output.

APPLIED TO OUR OWN SUBMISSION, IT FOUND TWO PAIRS WE SHOULD NOT HAVE SHIPPED
CLEAN. Run against the 28 pairs above and attached to each label's .zattrs: 22
ink pairs, median corroboration 1.00 -- but one (20250108000002-w027,
y8576_x17280) is corroborated 0.00, the second scan does not see that ink at
all. Of 6 negative pairs, one (20260126000000-w045, y12160_x12288) is only 5.5%
blank in both scans: shipped as certified blank, read by the other scan as
largely inked. Both flagged in place, not dropped.

UNCERTAINTY RANKING FOR RE-ANNOTATION. For all 62 paired segments we ship a 2D
per-segment map at 18 um/px of where the two scans agree, disagree, or are both
silent (out/consensus). The disagreement channel is a ranking of where a human
annotator's attention is worth most. It is 2D and is explicitly NOT a #192
deliverable -- #192 asks for true 3D and the pairs above are that. We built it
as one first, realised it was the projection #192 forbids, and demoted it.

AND WE SEARCHED FOR UNCALLED INK, WITH THE SENSITIVITY STATED. Two scans
average down independent noise, so a mark too faint for either detector alone
can clear a joint threshold. We searched min(z59, z78) over every letter-sized
box on sheet both scans cover and neither calls, and separately with a matched
filter for a run of eight letters along a baseline, swept over +-4 degrees.

Nothing. The line test -- the better-powered of the two, since a point maximum
over millions of boxes has a 4-7 sigma null from extreme-value statistics
alone -- is quiet on all 7 PHerc1667 segments (p >= 0.18) and all 32 PHerc0139
segments (zero at p <= 0.05, best 0.118). The point search produced four
PHerc0139 candidates, best p=0.015, but across 37 tests ~1.9 are expected at
p <= 0.05 by chance and none clears Bonferroni. The best-looking one reached
p=0.019 after 999 nulls and died to the render: 0.78 mm from the sheet edge,
under half a letter.

THE HONEST SIZE OF THAT NEGATIVE. "215 cm2 searched" would be misleading and we
nearly wrote it. What remains after removing called text, a 1.5 mm spillover
keep-out and a 1.5-letter edge keep-out is not open field -- it is narrow
ribbons between lines. Measured: of 215.2 cm2, only 52.4 cm2 has a full letter
of clearance and only 32.6 cm2 has room for a four-letter run. On one segment
the largest circle fitting inside the search region is 1.20 letters across. So
the claim is "no unnoticed letter over 52.4 cm2 of effective area, no unnoticed
word over 32.6 cm2" -- not over 215.

That kill also exposed a flaw we fixed rather than worked around. Our letter-box
accepted any box at least half on sheet, and 60.6% of the search area lay within
two letters of a sheet boundary, so the search was dominated by the region where
its own statistic misbehaves. Boxes must now be 95% on shared sheet and the
search is eroded 1.5 letters from every boundary; all numbers above are
post-fix, and the contaminated earlier ones are marked as such in
findings/CROSSENERGY_1667.md.

THE BOUND ON ALL OF IT. Both recipes are ScrollPrize models. Your page
describes the PHerc1667 maps as the product of a six-iteration pseudo-labeling
loop, and describes new_canon_autoresearch_recipe as trained on PHerc0139 and
validated on PHerc1667 pseudo-labels -- so the two are plausibly entangled and
part of the measured agreement may be shared model lineage rather than shared
ink. Accurately: this is cross-energy and cross-recipe, not fully independent.
Two energies also share the papyrus, so agreement does not separate ink from
sheet CONDITION. Every certificate states both bounds. If you can say whether
those two recipes share training data, it would sharpen the diagnostic
considerably.
```
