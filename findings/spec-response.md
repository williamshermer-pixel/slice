# Response to the ink-detection spec — what is already measured

Written 2026-07-27 against the build brief. Each section marked with what this
project has actually measured, because several items are already done, one is
already falsified, and one conflicts with a standing rule.

## Where the spec is confirmed by measurement

**§0 "no lead-like brightness spike to chase" — CONFIRMED, with a number.**
Brun et al. (PNAS 2016) found lead at 84 µg/cm² in *some* Herculaneum papyri, so
this was worth checking rather than assuming. Worked through, that concentration
in a 15 µm layer would make the ink ~5× more attenuating than the papyrus —
unmissable. Measured across 12 held-out tiles: the ink/bare difference is
+0.022 sd under a scale-free percentile split, and **the blind scroll shows the
same effect** (+0.069 sd, difference t = 0.34). These seven scrolls carry no
lead-driven attenuation contrast. The spec's framing is right and now has a
bound behind it. See `ink-physics.md`.

**§3 weave-filling / topography — CONFIRMED, and it is our best candidate.**
Arrived at independently today from the Mocella result that the ink "does not
completely penetrate the fibres". Built as `tools/weave.py`:

| feature | AUC (fresh tiles) | AUC (blind scroll) | gap |
| --- | --- | --- | --- |
| `weave_fill` | **0.746** | **0.541** | +0.206 |
| `weave_amp` | 0.743 | 0.565 | +0.178 |

`weave_fill` is exactly the spec's "ink pooling into the fiber texture" —
corrugation shallower than the local fibre lattice predicts.

**SUPERSEDED 2026-07-27 by audit. The 0.746 / +0.111 figures above are a
single favourable draw and must not be quoted.** Three independent
measurements, in order taken:

| source | AUC | null | excess | n |
| --- | --- | --- | --- | --- |
| this section, original | 0.746 | 0.635 | +0.111 | 14 |
| `out/scorecard/weave_fill_card.json` | 0.658 | 0.625 | +0.032 | 10 |
| audit recompute, fresh seed | 0.701 | 0.626 | +0.076 | 6 |

Every independent re-measurement is LOWER than the published headline. A
monotone decline across fresh draws is the signature of selection on the draw
(error 5 in the catalogue), not of a real effect.

**Actual status: excess +0.03 to +0.08, below this project's own 0.09 bar.
Dead by its own criterion.** Precision lift is x1.35 — of the top 5% of pixels
it ranks, 9.5% are ink against a 7.0% base rate. A papyrologist would see
nothing.

The claim that it "survives fresh draw, per-scroll breakdown, blind control and
parameter jitter" was made from an inline check, and **no `verify.py` artifact
for weave_fill exists in the repo.** Withdrawn until one does.

Note also the ranking was never draw-stable: on the audit's fresh draw
`weave_amp` scored +0.204 excess against weave_fill's +0.076, nearly 3x. The
"best candidate" designation was an artefact of which tiles were drawn.

**§4.2 independence test — BUILT, and it has killed three candidates.**
`tools/verify.py` runs fresh draw, per-scroll, ablation, weight jitter and both
controls. It killed candidates at r=+0.392 and r=+0.319 that had cleared every
prior gate. The spec is right that this is the trust standard; it is also the
single highest-yield thing built here.

**§6 validation harness — MOSTLY BUILT.** Cross-sampling agreement, held-out
eval, artifact controls and a per-candidate verdict all exist. Two gaps: no
depth-consistency check, and no per-candidate scorecard artifact.

## Where the spec needs correcting against this data

**§1 depth-pass stack sampling — ALREADY DONE, by the Challenge, for the
scrolls we can use.**

A "surface volume" in this bucket *is* the output of §1: the sheet traced,
resampled along its normal, and stored as `[depth, y, x]` where axis 0 is depth
through the sheet. Marching along mesh normals ourselves would reproduce work
already published for these seven scrolls.

The part of §1 that is NOT done applies to the **thirteen unread scrolls**,
which carry `segments/<id>/mesh/` and no flattened surface volume at all. That
is the segmentation problem, and it is GPU / C++ / VC3D work explicitly out of
scope for this repo (see CLAUDE.md).

What *was* missing is the spec's real point — "stop assuming the ink sits at a
fixed offset". Every measurement in this project averaged a depth band centred
on the sheet peak. A depth offset axis was added today and is now in the
search; a rapid probe showed transform responses varying 4× across ±18 layers,
which a peak-centred band cannot express.

**§2.4 letter-shape prior — BUILT AND FALSIFIED.** `tools/tracers.py` harvests
60 letterform templates from published ink maps at the measured hand (3.00 mm
letter, 0.35 mm stroke, 6.18 mm line pitch) and matched-filters them.

**Median gain over the raw field: −0.046.** Matched filtering *destroyed* signal
on 4 of 5 tiles. The reason is measured: correlation lengths of 13–45 px mean
letter instances are not independent samples, so integrating over letter area
does not buy √N. This is the same failure as an earlier letter-stacking attempt
(p = 0.365) reached by a different route.

The spec's framing — prior/filter, never generator — is the right instinct. But
on this data the filter subtracts rather than adds, and it should be scheduled
below the topography work rather than beside it.

## Where the spec conflicts with a standing rule

**§5 generative enhancement.** The project rule is: *no generative models on the
evidence, ever.* The spec's guardrails (image-to-image not text, condition
tightly on the prediction, always ship the raw alongside) are the right ones and
would make it defensible in a research setting.

For a Progress Prize submission I would still not do it. The asset here is a
tool that says "too weak to call" and is believed. Fifteen documented negatives
and a measured detection floor are credible precisely because nothing has been
retouched. An enhanced render, however well captioned, invites the one question
that costs everything. Recommend keeping the ban until there is a hit that
survives the harness — then revisit.

## Where the leverage actually is, revised

The spec's §7 puts segmentation first. That is almost certainly correct for the
field, and it is out of scope for this repo — no GPU, no mesh growing. Ranked by
what can move *here*:

1. **AUC instead of correlation.** Measured today: correlation against a sparse
   binary target saturates — synthetic ink injected at 100% of sheet contrast
   still only reached r = 0.484. Fourteen mechanisms were judged with an
   instrument that cannot move. Under AUC, four of them carry real ranking
   signal. This is a bigger correction than any feature.
2. **Depth offset** (§1's live half). Now in the search.
3. **Topography / weave-fill** (§3). Best candidate; needs more tiles for
   significance, not more cleverness.
4. **Ensembling across depth and parameters** (§2.3, §4.2). Partly built; the
   cheapest remaining false-positive killer.
5. **Self-supervised pretraining** (§2.2). Right in principle, needs a GPU —
   Modal or RunPod, not this laptop and not Vercel.

## The epistemic caveat that outranks all of it

Every label in this project is a **CNN's output**, not ink. On the blind scroll
the published model emits mid-range values nearly everywhere — fewer than 50
confidently-blank pixels per tile — because the ink was never sampled there at
1.9 voxels. Correlating with those labels measures a model's guess.

Real ground truth exists only for **physically opened fragments** with infrared
imaging, which the spec correctly flags in §4.3. Those fragments are in this
bucket (`PHercParis2Fr47`, `PHerc51Cr4Fr8`, and four others) but carry
**photos only — no CT, no labels**. Escaping the circularity requires the
Kaggle/scrollprize fragment download, which is the highest-value unblocked
acquisition on the list.
