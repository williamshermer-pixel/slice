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
