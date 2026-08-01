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
floor calibrated to a 0.2% false-positive rate on known-blank papyrus (at
that operating point it recovers 14.2% of known ink -- a high-precision,
low-recall label set, stated so nobody mistakes silence for absence), and a
scroll-level condition-control AUC separating ink from blank sheet of the
same preservation. A QC gate verifies the depth claim on ink pairs rather
than asserting it.

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
shipped INK crop and removes pairs that fail — a projected label cannot pass
it, and our own first version was exactly such a projection and was discarded.
(Blank pairs carry no ink and therefore no depth to vary; the gate does not
apply to them.)

2. THE SURFACE-CONFOUND CONTROL (#192's stated fear, measured). Every pair
carries the scroll-level condition-control AUC (one measurement per scroll,
stamped on each pair -- not a per-pair measurement): ink separated from blank
sheet INSIDE the
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
All pairs are from PHerc0139. 12.7% of labelled ink columns carry a resolved
depth; the other 87.3% are shipped as code 3 (ink present, depth ambiguous) --
we would rather withhold a depth than invent one. The ink floor is
high-precision and LOW-RECALL: at its 0.2% false-positive operating point it
recovers 14.2% of known ink, so code 2 means "the detector saw nothing here",
not "there is nothing here". Two of the 28 pairs are committed in
samples/pairs/ so a reviewer can open a working zarr immediately; the full set
regenerates from the public bucket with the commands in the README.
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
