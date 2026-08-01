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
generation method). Each pair ships a measured quality certificate: an ink
floor calibrated to a 0.2% false-positive rate on known-blank papyrus, which
recovers 14.2% of known ink at that operating point (high precision, low
recall, stated so nobody mistakes silence for absence), and a scroll-level
condition-control AUC separating ink from blank sheet of the same
preservation. A QC gate verifies the depth claim on ink pairs rather than
asserting it. A cross-scan audit against the scroll's second published energy
flagged five of our own 28 pairs; the flags ship in the labels' metadata.

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
Ink labels are a stated bottleneck (villa #192, #193), and #192 names the risk
that labels teach a model the surface rather than the ink. This submission is
aimed at that.

1. Ready-to-run 3D ink labels (#192). 28 image/label pairs from PHerc0139 as
plain zarr: 512-square tiles, image and label together, nothing to crop or
preprocess. Codes are 0 unlabelled, 1 ink, 2 blank, 3 ink present but depth
ambiguous. Depth is recovered, not projected. The ink model reads a fixed
62-layer window, so we slide that window through the stack and give every
pixel a response profile. The peak is its depth, narrowed by the crop's own
intensity profile, which cannot see ink but locates the sheet the ink must lie
on. Flat profiles are labelled ambiguous instead of guessed. A QC gate checks
that depth actually varies across every shipped ink crop; our own first
version was a projection and it failed. 12.7% of ink columns carry a resolved
depth, the rest ship as code 3. The floor that certifies blank regions
recovers 14.2% of known ink at a 0.2% false positive rate, so code 2 means the
detector saw nothing there, not that nothing is there. Two pairs are committed
so a reviewer can open a working zarr in seconds; the rest regenerate from the
public bucket with one command.

2. The surface confound, measured. Each pair carries its scroll's
condition-control AUC: ink against blank sheet inside the same text block,
same preservation, same damage. 0.96 on this scroll's curated segmentation,
0.84 on auto-grown ones. This control killed one of our own earlier
candidates, which scored r 0.44 held out and 0.21 on blank papyrus. It was
reading preservation.

3. Calibration results any pipeline on these models can hit. Reading layers
27 to 89 instead of the stack centre moved agreement with published Scroll 1
calls from AUC 0.654 to 0.944. Letter heights taken from connected components
run 3 to 5x small (Scroll 1's known 3.00 mm hand reads as 0.58 mm); a
band-FWHM measure gives 2.94. Fine-tuning gains are segmentation-bound: +0.094
AUC on curated segments against +0.011 on auto-grown, so flattening quality is
the wall, not model knowledge.

4. A cross-scan check that audited our own labels. PHerc0139 was scanned at 59
and 78 keV and both ink maps are published, so any label on this scroll can be
asked: does the second scan corroborate this? Run against our own 28 pairs it
flagged five. Three are footprints their own source map does not call at ds8,
a labelling question rather than a cross-energy one. One is a genuine
cross-energy disagreement (source calls it at 0.70, the second scan at 0.17).
One negative pair we shipped as certified blank is called ink by BOTH maps
over 86.5% of its area. Each is flagged in place with a verdict naming which
map disagrees. Scroll-wide, the two published maps agree on 58.9% of each
other's calls (median over 37 segments; Jaccard 0.417 against a
density-preserving spatial null of 0.030). Two bounds travel with every
certificate: the two recipes are plausibly entangled through training data,
and 1.1 um data is cleaner than 2.4 um by your own measurement, so this is
cross-energy and cross-recipe, not independent.

5. A search of the sheet neither map calls, with its sensitivity measured
rather than assumed. No survivors: 35 of 37 segments produced a usable
area-matched paired null and none reaches p 0.05 (smallest 0.090). Of 67.1 cm2
searched, only 28.7 cm2 can host a letter-sized disc, and a synthetic letter
planted at the median amplitude of real calls scores 2.72 against a null p95
of 2.45. A bounded negative, and it says so.

One disclosure. The first version of the cross-scan instrument was broken: a
warp applied with an inverted sign, a null compared at the wrong call density,
a test suite that could not fail. Adversarial review caught all of it before
this submission. Everything above is from the corrected rerun, the pipeline is
now gated by a positive control that plants known shifts and synthetic ink and
fails unless both are recovered, and the full failure catalog with the check
that now guards each bug is findings/CROSSENERGY_1667.md. Results for two
other scrolls were measured with the broken instrument and are withdrawn
rather than corrected.

The viewer everything runs on is browser-native, no install or login,
streaming OME-Zarr from the public bucket: slice-site-alpha.vercel.app, with
the measured ink band marked on the depth control so the calibration above is
usable, not just documented.

Known limits: crops are 1.16 mm square, smaller than one letter of this hand,
so these are training tiles, not readable views. All pairs are from PHerc0139.
The cross-scan check is letter-scale and carries no depth.
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

## ADDENDUM — cross-energy corroboration on PHerc0139 (append to the end of the long answer)

```
Added the same day, and scoped narrowly on purpose. PHerc0139 was scanned at
two X-ray energies (59 keV and 78 keV) and its ink maps were published twice,
with different recipes, months apart. That allows a question no single map
answers: does a second scan corroborate this label? We could not find that
comparison published, so we built it, and we ran it against our own pairs
above.

Applied to the 28 pairs, the check writes into each label's metadata whether
the label's footprint is called by its own source map at ds8 resolution and
whether the 78 keV scan corroborates it. Of 22 ink pairs the median
corroboration is 1.00 and the mean 0.836 -- but the check found four ink pairs
and one negative pair that do not hold up, and it names which map disagrees.
Three of the four are footprints their own 59 keV source map does not call at
ds8 (0.00, 0.11, 0.00) -- a labelling question rather than a cross-energy one.
One (20250108000003-w028, y9088_x14336) is a genuine cross-energy
non-corroboration: the source calls it at 0.70, the independent scan at 0.17.
One more is the reverse and the most interesting in the set
(20250223000000-w059, y11776_x8320): the source map does not call it and the
independent scan calls it at 0.98. And one pair we shipped as certified blank
(20260126000000-w045, y12160_x12288) is 86.5% called ink by BOTH maps -- not
disputed between scans, contradicted by both. All five are flagged in place
rather than dropped; which are labelling errors and which are detector
disagreements is your annotation team's call, not ours.

On the scroll as a whole (all 37 segments with both maps): the two maps agree
far above a density-preserving spatial null -- median top-decile Jaccard 0.417
against a null of 0.030, median enrichment 14.2x, every segment at the null's
p floor of 0.04 -- and at a top-decile call they agree on 58.9% (median) of
each other's calls. Two bounds
travel with that number and with every certificate: the two recipes are
plausibly entangled through training data (your Open Problems page describes
the 78 keV recipe as trained on PHerc0139 and validated on PHerc1667
pseudo-labels), so agreement may partly reflect shared lineage; and 1.1 um
data is cleaner than 2.4 um by your own measurement, so some disagreement is
resolution, not error. This is cross-energy and cross-recipe -- not
independent -- and it is aimed at a question your page asks directly: telling
"no ink" from "no ink recovered yet".

We also searched the sheet neither map calls, with a min(z59, z78) statistic
against an area-matched paired null: for each shift both the registered and
de-registered maxima are taken over the same intersection region, so the
comparison is like-for-like. No survivors. 35 of 37 segments produced a usable
null (median 99 matched draws); zero reach p <= 0.05 and the smallest p is
0.090.

Two limits travel with that negative and we would rather state them than let
them be found. First, coverage: the uncalled region is ribbons between text
lines, and of 67.1 cm2 searched only 28.7 cm2 can host a letter-sized disc and
10.2 cm2 has room for a four-letter run. Second, sensitivity, measured by
planting synthetic ink rather than assumed: a single letter at the median
amplitude of real published calls lands only just above the null's 95th
percentile (2.72 against 2.45). This search has real power for
stronger-than-typical marks and multi-letter features, and is marginal for one
faint letter. It is a bounded negative, not a clean sheet.

Full disclosure that belongs with this: the first version of this instrument
had a warp applied with the wrong sign, a null that compared against the
wrong call density, and a test suite that could not fail. All of it was
caught by adversarial review before submission, fixed, and re-run; the
pipeline is now gated by a positive control that plants known shifts and
known synthetic ink and fails unless they are recovered
(tools/positive_control_xe.py). The failure catalog with the check that now
guards each bug is findings/CROSSENERGY_1667.md. Results for PHerc1667 and
PHerc0814 were measured with the defective instrument and are withdrawn
rather than corrected; the corrected reruns are August work.
```
