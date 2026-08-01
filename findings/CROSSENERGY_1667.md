# Cross-energy corroboration on PHerc0139 — a diagnostic, its bugs, and what survived

*2026-07-31, rewritten the same night after two adversarial reviews (a second
model on the code, a third on the claims) found the first version's instrument
defective. The bugs, the checks that now guard them, and the corrected numbers
are all below. Nothing in this file is quoted from a run of the defective
instrument.*

Tools: `tools/crossenergy_1667.py` (registration + agreement),
`tools/conjunction_1667.py` (the search), `tools/certify_pairs_crossenergy.py`
(the pair certificate), `tools/positive_control_xe.py` (the gate — plants known
shifts and known ink, fails when the instrument is broken),
`tools/effective_area.py`. Data: `out/xe_PHerc0139/*.json`.

## The lever

PHerc0139 was scanned twice and its ink maps published twice:

| | 59 keV | 78 keV |
| --- | --- | --- |
| surface volume | `1.129um-…-L1`, 2.258 µm/voxel | `2.399um-…`, 2.399 µm/voxel |
| ink map recipe | `mrg20736-1um-s1z2` | `new_canon_autoresearch_recipe` |
| published | 2026-07-09 | 2026-04-17 |

37 of its 38 segments carry both maps. For any ink label on this scroll we can
therefore ask a question no single map answers: does a second scan, through a
different reconstruction and a different recipe, corroborate this?

## How independent, exactly — less than it looks

The *scans* are independent in physics: photon energy, reconstruction,
flattening run. The *maps* are not known to be. Both recipes are ScrollPrize
model output, and the project's own 2026 Open Problems page describes
`new_canon_autoresearch_recipe` as found by an agent swarm **training on
PHerc0139 data** and validated against **PHerc1667 pseudo-labels** — pseudo-
labels produced by the other lineage. On this scroll the two maps are therefore
plausibly entangled through training data, and part of any agreement measured
below may be shared model lineage rather than shared ink.

The page also states that 1.1 µm data yields cleaner ink results than 2.4 µm,
so the two maps are not peers: part of their *disagreement* is a known
resolution asymmetry, not error in either.

Accurate name for this method: **cross-energy and cross-recipe**. Not
"independent". Both bounds are stated on every certificate it produces.

## Registration

The two canvases differ by the voxel ratio; resizing the 78 keV map onto the
59 keV canvas by that ratio aligns them to a residual local warp that a block
phase-correlation field measures and removes. The field is **measured and
recorded per segment** in each certificate (`registration_measured`: trusted
block count, median and IQR displacement). An earlier version of these
certificates hardcoded a global "sx=1.000 sy=1.000 dy=0 dx=0, IQR ~45 px" onto
every array — numbers from an ad-hoc exploration that no tool in this repo
performs. That was fabricated provenance and is retracted; certificates now
carry only what the pipeline measured on that segment.

The warp itself shipped with an inverted sign — phase correlation peaks at −s,
and the code applied +s, so the "registration" step *degraded* alignment on
every segment (measured on 20250108000000: letter-scale r 0.605 unwarped,
0.420 as-coded). `tools/positive_control_xe.py` now plants a known shift and
requires the warp to recover it and to *improve* correlation before any run is
believed.

## Result 1 — agreement between the two maps (corrected instrument)

Calls are each map's top decile, integrated over a letter-sized box (≥95% on
shared sheet — a box half off-sheet divides by a shrinking denominator and
manufactures edge candidates). The null preserves call *density*: the rolled
map's sheet mask rolls with it, and the Jaccard is scored on the overlap of
the two sheets. The first version rolled calls off a stationary sheet,
compared against ~1.8% density instead of 10%, and inflated enrichment about
six-fold (a certificate shipped 60.4× where the density-preserving value is
9.6×).

Across all 37 paired segments:

- letter-scale high-passed Pearson r (it was once mislabelled a Spearman; it
  never was one): median **0.455**, range 0.181–0.641
- top-decile Jaccard: median **0.417** against a density-preserving rolled
  null of **0.030** — enrichment median **14.2×**, range 5.8–62.7×, every
  segment at p = 0.04, which is the *floor* of a 24-roll null and not a
  measurement of how small p is
- registration actually applied: median 16 trusted blocks per segment, median
  |dy| 3.1 px, median IQR 8.6 px — recorded per segment, not asserted

For scale on what the bugs cost: the same median enrichment read 25.1× before
the density-preserving null, and the certificate on one segment read 60.4×
where the corrected value is 9.6×.

The disagreement is the half the annotation team should see: at a top-decile
call the two maps agree on **58.9%** (median) of each other's calls on this
scroll.
Given the lineage entanglement above, the true ink agreement may be lower;
given the resolution asymmetry, some disagreement is expected and benign. The
number bounds how far one published map can serve as ground truth for an
annotator drawing letters over it.

## Result 2 — the certifier, run on our own 28 pairs

`certify_pairs_crossenergy.py` writes into each #192 pair's `.zattrs`: does
the 59 keV source map call this label's footprint at ds8, and does the 78 keV
scan corroborate it? The first version read **only the 78 keV map** and
misdiagnosed both of its headline findings — an ink pair scored
"single-scan-only" that *neither* scan calls (a label-derivation question, not
a cross-energy one), and a "certified blank" blamed on the second scan when
89.9% of it is called by *both*. Verdicts now name the map that disagrees, or
refuse to assign blame when the home map never called the footprint.

Corrected results across the 28 pairs. 22 ink pairs: median corroboration by
the 78 keV scan **1.00**, mean 0.836. 6 blank pairs: median both-scans-blank
**1.00**. But four ink pairs and one blank pair do not hold up, and the
verdicts now say *which* map disagrees:

| pair | 59 keV source | 78 keV | reading |
| --- | --- | --- | --- |
| `20250108000002-w027 … y8576_x17280` | **0.00** | 0.00 | neither map calls this footprint — a label-derivation question, not a cross-energy one |
| `20250108000004-w029 … y7936_x12160` | **0.11** | 0.11 | same: barely called by either |
| `20250223000000-w059 … y11776_x8320` | **0.00** | 0.98 | the *independent* scan calls it strongly and the source map does not — the most interesting pair in the set |
| `20250108000003-w028 … y9088_x14336` | 0.70 | **0.17** | a genuine cross-energy non-corroboration: source calls it, second scan does not |
| `20260126000000-w045 … y12160_x12288` (blank) | — | — | **86.5% of this "certified blank" crop is called ink by BOTH maps.** Not disputed between scans; contradicted by both |

Only the fourth row is a cross-energy disagreement in the sense originally
claimed. Three are labels their own source map does not support at ds8, and
one is a negative pair that both maps contradict. The first version of this
tool reported one finding and attributed it to the wrong scan; the corrected
tool reports five and attributes each correctly. All are flagged in place
rather than dropped — which of them is a labelling error and which is a real
detector disagreement is a judgement for the annotation team, not for us.

## Result 3 — the conjunction search, and the honest size of its negative

Statistic: max over the uncalled search region of min(z₅₉, z₇₈) in letter
boxes. Search region: shared sheet, minus called text plus a 1.5 mm spillover
keep-out, minus 3 letters from every sheet edge (the letter-scale high-pass is
biased positive within ~3 letters of an edge in *both* maps at the same place
— a shared artifact the roll null cannot see; 1.5 letters left a quarter of
the search area inside the biased band).

The null is **area-matched and paired**: for each shift, both the registered
and the de-registered maxima are computed over the *same* intersection region,
and p is the fraction of pairs where de-registered beats registered. Two
earlier nulls died — one dropped +5σ called-text values into the search window
(the null *exceeded* the observation on most segments; "zero survivors" was
unearned), one was area-mismatched and produced zero valid draws on
ribbon-shaped regions.

Result: **no survivors.** 35 of the 37 segments produced a usable paired null
(median 99 matched draws each; two segments were skipped rather than reported
— one could not reach the draw floor, one had too little search area). Across
those 35, 66.5 cm² of uncalled sheet, **zero segments** reach p ≤ 0.05; the
smallest p is 0.090 and the range runs to 0.490. No candidate to render, no
candidate to argue about.

Sensitivity, measured by the positive control rather than asserted: a single
synthetic letter planted in both maps at the *median amplitude of real
published calls* lands just above the paired null's 95th percentile (J = 2.72
against 2.45 on the control segment). Single-letter detection at typical ink
strength is therefore **marginal** — this search has real power only for
stronger-than-typical marks or multi-letter features, and its negative must be
read with that limit attached.

Coverage, honestly sized (`effective_area.py`, which now imports the search's
own construction from `conjunction_1667.build_search` so the sized region and
the searched region cannot drift apart): the uncalled region is narrow ribbons
between text lines, not open field. Raw searched area **67.1 cm²**; area where
a letter-sized disc actually fits **28.7 cm² (42.7%)**; area with room for a
four-letter run **10.2 cm²**. A negative over the raw figure would be
misleading and is not claimed. The earlier "line test" (a matched filter for
text lines) is **withdrawn entirely**: its null was the identity operation —
translation-equivariance returned the observation to the last decimal — so it
had zero power, and with 16 nulls its "p ≤ 0.05" flag was arithmetically
unreachable. Its results measured nothing and are not replaced tonight.

## The failure catalog — every bug, and the check that now guards it

Found by adversarial review (a second model over the code, a third over the
claims against the funder's documents), 2026-07-31 evening. Kept here because
the project's rule is that a found bug means a missing check, and the checks
are the durable product.

| bug | consequence | guard now |
| --- | --- | --- |
| warp sign inverted | registration degraded on every segment; all agreement numbers understated | positive control plants a shift, requires recovery + improved r |
| Jaccard null lost call density | enrichment inflated ~6× | null rolls the sheet mask with the calls |
| conjunction null rolled text into the window | null > observation; "no survivors" unearned | area-matched paired null |
| line-test null was the identity | zero power; planted ink made it *less* significant | test withdrawn; any successor must pass planted-ink recovery |
| line-test NULL_N=16 | "p ≤ 0.05" impossible by arithmetic | p-floor asserted against the claim threshold |
| certifier read one map | both headline "bad pairs" misdiagnosed | verdicts computed from both maps, blame requires evidence |
| certificates asserted an unperformed measurement | fabricated provenance, public | certificates carry only per-segment measured values |
| letter-box accepted 50% off-sheet | edge candidates manufactured | ≥95% coverage + 3-letter edge erosion |
| test harness greps and tautologies | 13/13 "passing" while all of the above shipped | the positive control is the gate; string-greps removed |

## What this is worth

It is a **diagnostic**, aimed at questions the funder's 2026 Open Problems
page asks in its own words: telling "no ink" from "no ink recovered yet", and
"stronger diagnostics" for cross-scroll generalization. It is **not** a #192
deliverable (that issue demands true-3D labels; the 2D consensus rasters built
here earlier were exactly the projection it forbids and are demoted to an
annotator overlay). It does **not** touch #193's hard case (labels where no
segmentation exists); it requires a segmentation and two published maps.

## Status of PHerc1667 and PHerc0814

Both were measured with the defective instrument. Every number previously
reported for them — including the whole-scroll agreement tables and the "~237
cm² searched, nothing found" claim — is **void and withdrawn**, not corrected,
because there was no time to rerun them before the July deadline. The corrected
instrument reruns them in August. Nothing about them is claimed in the July
submission beyond their existence as cross-energy pairs.
