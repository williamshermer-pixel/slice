# Second overnight — 2026-07-27

Written while the run is going. Everything below is measured. Where a number
came out badly it is reported badly, because the negatives are the asset.

## The headline

**The scroll that was read is in WORSE physical condition than the ones that
were not.** It was not read because it was healthier. It was read because it
was flattened.

| measure | Scroll 1 (read) | median of the others | |
| --- | --- | --- | --- |
| height noise floor | 2.05 µm | 1.61 µm | 1.28× worse |
| correlation length | 101 µm | 35 µm | 2.86× worse |
| fibre anisotropy | 0.135 | 0.208 | 0.65× worse |
| sheet contrast | 95.6 | 94.4 | same |
| scan resolution | 1.76 µm/vox | 1.67 µm/vox | same |

This kills a comfortable assumption. Every "we can't read the others because
they're in worse shape" story is wrong for this set of seven. Segmentation is
the difference, not preservation.

## The negative control was measuring ink

The first overnight run killed every candidate with a "negative control on
blank papyrus". That control was broken, in a way worth recording carefully
because it is easy to repeat.

It selected control segments by **whole-map** ink coverage (< 2%), then scored
them through `eval_variant`, which **requires 5–85% ink coverage in the crop it
actually measures**. Those two numbers are not the same: a segment can be 99.5%
blank overall while the central 4×4-chunk window every measurement uses sits
directly on a column of text.

So the control only ever ran on crops containing 5–85% ink. It was measuring
ink detection and reporting it as failure. Measured directly on the current
control set, before the fix:

| control tile | whole-map coverage | coverage of the tested crop |
| --- | --- | --- |
| PHerc0343P | 0.0067 | 0.0000 |
| PHerc0500P2 | 0.0051 | **0.0220** |
| PHercParis4 | 0.0004 | 0.0000 |
| PHerc0343P | 0.0132 | 0.0093 |
| PHerc0500P2 | 0.0178 | **0.0859** |

Controls are now selected on the crop that is actually scored, verified
≤ 0.5% ink. `pack.crop_coverage()` exists for this and nothing should choose a
control any other way.

### So were the first run's candidates killed wrongly?

No — but its evidence was wrong. Re-run against a verified-blank control
(`tools/recheck.py`, 8 controls across 4 scrolls, 13 held-out tiles):

| candidate | held-out \|r\| | verified blank | blind scroll | verdict |
| --- | --- | --- | --- | --- |
| offaxis+hfenergy+chandark | 0.371 | 0.123 | 0.108 | dead |
| offaxis | 0.356 | 0.127 | 0.108 | dead |
| offaxis+hfenergy | 0.333 | 0.177 | 0.105 | dead |
| disorder+offaxis+sharp | 0.212 | 0.222 | 0.062 | dead |

The blank scores are roughly **half** what the broken control reported (0.12–0.22
against 0.21–0.47), so the original numbers were inflated. But they are still
above threshold, and the candidates also fire at ~0.11 on the blind scroll,
where the ink was never sampled and correlation cannot be ink. Two independent
controls agree. The conclusion survives; the evidence for it did not.

## Partial correlation — removing condition instead of taxing it

Penalising a candidate for firing on blank papyrus taxes the confound. Partial
correlation removes it: residualise both the feature and the ink target on
measured sheet brightness, local contrast, fibre coherence and curvature, then
correlate what is left.

| feature | raw | partial | blank raw | blank partial |
| --- | --- | --- | --- | --- |
| offaxis | 0.370 | **0.381** | 0.166 | 0.175 |
| hfenergy | 0.392 | 0.258 | 0.069 | 0.200 |
| pca_c1 | 0.132 | 0.152 | 0.125 | **0.057** |
| sharp | 0.187 | 0.076 | 0.338 | 0.045 |
| rti_height | 0.124 | 0.173 | 0.119 | 0.076 |

`offaxis` is the interesting row: partialling does not touch it (0.370 → 0.381),
so whatever it keys on is **not** in those four condition covariates — yet it
still fires 0.175 on blank sheet. Its confound is real but unidentified. That
is a concrete, well-posed open question rather than a dead end.

Only `pca_c1` passes the survival test (partial > 0.10, blank partial < 0.06),
marginally, and it is a sheet-brightness component. Not a lead yet.

## The mistake this found in our own run

Scrolls were being split into tune/held-out **alphabetically**. That put
`PHerc0172` in the tuning set. Its finest surface volume is 7.91 µm/voxel:

> 15 µm ink layer ÷ 7.91 µm/voxel = **1.9 voxels**, against the ~3 needed to
> resolve a feature at all.

The ink on PHerc0172 was never sampled. Half of every tuning signal in the
first two runs came from a scroll that is physically incapable of showing ink.

Voxels through the ink layer, per scroll:

| scroll | µm/voxel | voxels | role now |
| --- | --- | --- | --- |
| PHerc0139 | 1.129 | 13.3 | tune |
| PHerc0814 | 1.129 | 13.3 | tune |
| PHerc1667 | 1.129 | 13.3 | held-out |
| PHercParis4 | 1.764–2.42 | 6.2–8.5 | held-out |
| PHerc0343P | 2.215 | 6.8 | held-out |
| PHerc0500P2 | 2.215 | 6.8 | held-out |
| **PHerc0172** | **7.910** | **1.9** | **physics control** |

### The blind scroll is now an asset

PHerc0172 carries text and has published ink detections, but its scan never
sampled the ink layer. So **any measure that correlates there is not measuring
ink**, whatever it scores elsewhere.

That is a stronger control than blank papyrus. The blank control argues from an
absence of ink; this one argues from an absence of *resolution* on sheets that
do carry writing. It catches confounds the blank control cannot — anything
keyed to layout, sheet geometry, or where a scribe chose to write.

Both controls are now inside the objective:

```
score = heldout_median  -  1.5 * blank_papyrus_r  -  1.0 * max(0, blind_scroll_r - 0.05)
```

## Condition varies enough that a single global detector is the wrong object

| measure | min | max | spread |
| --- | --- | --- | --- |
| correlation length | 15.8 µm | 114.7 µm | **7.3×** |
| sheet contrast | 41.1 | 119.6 | **2.9×** |
| fibre anisotropy | 0.135 | 0.329 | **2.4×** |
| height noise floor | 1.21 µm | 2.16 µm | 1.8× |

Pooling a median correlation across scrolls this different is a weak summary.
Future work should stratify or partial condition out rather than search for one
universal measure.

## Three mechanisms tested. Three more negatives.

Bringing the project total to **twelve**.

| mechanism | held-out r | on blank | after controls | verdict |
| --- | --- | --- | --- | --- |
| RTI specular relief (`rti_height`) | +0.120 | 0.042 | **+0.056** | dead |
| RTI multi-light variance (`rti_specvar`) | +0.099 | 0.088 | −0.034 | dead |
| RTI slope (`rti_slope`) | +0.121 | 0.090 | −0.015 | dead |
| Depth PCA component 2 | +0.150 | 0.053 | **+0.070** | dead |
| Depth PCA component 1 (43% var) | +0.123 | 0.100 | −0.028 | dead |
| Letterform matched filter (tracers) | see below | — | — | dead |

### RTI — done properly, still nothing

The earlier raking-light attempt scored r=0.02 and was diagnosed as
"differentiates away the signal it needs". That diagnosis was right but the fix
did not rescue it. This implementation does the three things the crude version
did not: sweeps 16 azimuths and keeps the variance (so no stroke orientation is
invisible), applies normal-unsharp enhancement, and band-passes at stroke scale
*before* differentiating so it is not taking normals of a 30 µm noise floor.

Best result after controls: **+0.056**. RTI is a display technique — it
re-encodes relief the scan already contains. The relief is not there.

### Depth PCA — the good idea that did not pay

The reasoning was sound: multispectral conservators run PCA across bands
because the ink/substrate separation often lives in a combination and no single
band shows the text. We have 109 depth layers and every previous experiment
collapsed depth before doing anything.

Basis fitted on tune scrolls only, unsupervised, fixed loadings applied
unchanged to held-out scrolls — so there is no leakage and no per-tile
cherry-picking of "the component that worked". Best is PC2 at **+0.070**.

Notably PC1 (43% of variance) scores +0.123 raw but 0.100 on blank papyrus —
it is a sheet-brightness term, exactly the confound.

### Tracers — matched filtering makes it worse

Templates cut from donor segments on tune scrolls, tested on held-out scrolls
that never donate. 60 letterform templates harvested at the measured hand.

**Median gain over the raw field: −0.046.** Matched filtering *destroyed*
signal on 4 of 5 tiles.

The reason is the blocker flagged in the previous handoff, now measured:
correlation lengths of 13–45 px in the field. Letters sit inside one
correlation length of each other, so integrating over letter area does not
average independent noise. The area argument — 75,000 voxels per letter — only
buys √N when the N samples are independent, and they are not.

This is the same failure as the earlier letter-stacking result (p = 0.365),
confirmed by a second, independent route.

## Negative thirteen — and it is a failure in our METHOD, not the physics

After ~5,700 tested variants the pack fired an alert. The candidate,
`offaxis + rti_height + rti_specvar`, cleared every gate that exists:

| | |
| --- | --- |
| held-out ink, 4 scrolls | +0.392 |
| verified-blank papyrus | 0.082 |
| blind scroll | 0.056 |
| partial r, condition removed | 0.311 |

The falsification battery (`tools/verify.py`) killed it on four of five tests:

| test | result |
| --- | --- |
| fresh tile draw, unused seed | **+0.392 → +0.053** |
| per scroll | Scroll 1 +0.177, PHerc0500P2 **−0.117** — opposite signs |
| ablation, each term alone | 0.001 / 0.023 / 0.012 |
| ablation, drop any one term | 0.019 / 0.024 / 0.057 |
| weight jitter ±8% | **0/10 survive** |

The weights tell the story: −3.84 / +3.76 / +0.98, near-equal and opposite. A
razor-thin difference between two z-scored maps. No term does anything alone,
no pair does anything, and only that exact triple at those exact weights
scores.

### The actual bug

The hill-climb mutated the best variant against **one fixed held-out draw for
the entire run**. After thousands of variants that set was not held out any
more — it was training data. Selection on the validation set manufactures a
winner given enough iterations, and 1,872 variants reached the control stage.

This is worth publishing. It is the same class of error as the earlier
r=+0.368 collapse, arrived at by a completely different route, and it is the
error most likely to be sitting inside other people's ink-detection pipelines.

### The fix, now in `dogs.py`

- **Rotating selection set** — held-out tiles are re-drawn every 120 variants
  and the incumbent best is voided, so no single draw can be memorised.
- **Disjoint confirmation set** — 20 segments that never influence selection.
  Nothing can alert without holding there.
- **Jitter as a precondition** — ±10% weight perturbation must retain 60% of
  the score in over half of trials, checked *before* alerting rather than
  afterwards.
- **Weight clamp at ±1.5** — unbounded multiplicative drift is what allowed a
  knife-edge cancellation to form at all.

## Negative fourteen — `disorder + localsd`, same signature

The best candidate of the nested-validation run. It passed both controls, which
nothing before it had done cleanly, and still died:

| test | result |
| --- | --- |
| fresh tile draw | **+0.319 → +0.024** |
| per scroll | Scroll 1 +0.062, PHerc0500P2 **−0.032** |
| ablation | `disorder` alone +0.160; `localsd` contributed nothing |
| jitter | **0/10** |
| verified-blank control | 0.099 PASS |
| blind-scroll control | 0.040 PASS |
| partial r | **0.065** — ~80% of the raw score was sheet condition |

Passing the controls while failing the fresh draw is the important combination.
It means the controls are now doing their job and the remaining failure is pure
selection effect, not confounding. Those are different diseases and they need
different cures.

## The pattern across all fourteen

`offaxis` appears in six of the eight highest-scoring families ever produced.
It scores r ≈ 0.39 against published ink, and it is the one measure whose
correlation SURVIVES partialling out brightness, contrast, coherence and
curvature (0.370 → 0.381) while still firing 0.175 on verified-blank sheet.

So there is something real, strong, and repeatable in the off-axis orientation
signal that is not ink and is not any of the four condition covariates measured
so far. Identifying it is the most concrete open question this project has.

## POSITIVE CONTROL — how do we know the negatives are not false?

Fourteen mechanisms declared dead, and every tool in this project is built to
kill. Nothing measured whether the killing was CORRECT. So: spike-in recovery.
Inject a synthetic ink layer at the published ink positions, at a known
contrast, 15 µm thick converted to layers per scan, and find the amplitude at
which the ordinary pipeline detects it.

**First, alignment.** Feeding the ink mask itself in as the detector returns
**r = 1.000** on 6 of 6 tiles, with `ds` exactly 8.0 and no accumulated drift.
The scorer is correctly registered; the correlations in this project are
computed on properly aligned data. This needed checking and it passed.

**Then the sweep** (detector: high-pass of the depth band, near-optimal for an
injected offset, so this is BEST-CASE sensitivity):

| injected δ | % of sheet contrast | median r | significant |
| --- | --- | --- | --- |
| 0 (real data) | 0% | 0.089 | 0% |
| 8 | 8.4% | 0.139 | 0% |
| 16 | 16.8% | 0.179 | 25% |
| 24 | 25.2% | 0.215 | 50% |
| **32** | **33.6%** | **0.250** | 50% |
| 48 | 50.4% | 0.317 | 75% |
| 64 | 67.2% | 0.379 | 75% |
| 96 | 100.8% | 0.484 | 100% |

### The detection floor

**≈ 34% of sheet contrast**, or ~32 of 255 grey levels, to reach r = 0.25.

Note that even injecting ink at 100% of sheet contrast — a physically absurd
signal — only reaches r = 0.484. Papyrus texture variance is comparable to the
injected signal and ink covers ~5% of area, so a linear correlation readout
against a sparse binary target is structurally capped well below 1 for anything
short of a near-perfect detector.

### What this licenses us to say, and what it does not

DOES: no measure tried here finds anything above roughly a third of sheet
contrast. Given that carbon ink on carbonised papyrus was measured at r=+0.002
with 88% distribution overlap, the real contrast is orders of magnitude below
that floor. The negatives are consistent with the physics.

DOES NOT: it does not show ink is undetectable in these scans. **The ground
truth used throughout this project exists precisely because published CNN
models DO detect ink in this data.** So ink is recoverable — just not by
hand-crafted texture statistics read out through a linear correlation, which is
what all fourteen mechanisms were.

That is the correct scope of the negative result, and it should be stated that
way in the submission. "Fourteen hand-crafted mechanisms fail, here is the
sensitivity floor that bounds the claim" is honest and useful. "Ink cannot be
detected" would be false and the annotation team would know it immediately.

## Infrastructure built (reusable, in `tools/`)

| file | what it is |
| --- | --- |
| `pack.py` | shared layer: disk tile cache, controls, spatial-null scoring, strata |
| `rti.py` | RTI specular enhancement + relight sweep renders |
| `depth_pca.py` | fixed depth basis, unsupervised, fitted on tune scrolls only |
| `tracers.py` | letterform harvest, baseline grid, FFT matched filter, N_eff |
| `condition.py` | per-scroll condition measurement |
| `dogs.py` | the search, with both controls inside the objective |

Two fixes worth recording because they were silent:

- **Tiles were 250 MB each in RAM** (full depth stack). Cropped to the sheet
  band and held as uint8: 15 MB. Twelve parallel workers went from impossible
  to routine.
- **`nightshift.py` parses `sys.argv[1]` as a float at import time.** Importing
  it from `dogs.py --run 12 0` throws, and a `try/except` around the import
  silently dropped the entire 8-feature texture bank. One run launched with 11
  features instead of 19 and reported nothing wrong. `dogs.py` now aborts if
  the bank is short.

## The fix that mattered most, restated

The first overnight run produced candidates at held-out r = +0.44 that scored
|r| = 0.21–0.47 on blank papyrus. Every high scorer was a papyrus-condition
detector. The control ran *after* the search, so the search climbed into the
trap all night and got killed there repeatedly.

It is now inside the objective. Live confirmation from the current run: the
feature `offaxis` scored raw **+0.258** — the old swarm would have fired an
alert — and fires 0.209 on blank papyrus, so it now scores **−0.056** and the
search walks away from it.

## What has not been done

- No letters were read. Nothing here is a reading.
- The Greek language-prior lane is still untouched and still open.
- Condition-stratified search (the obvious consequence of the spread table
  above) is designed but not built.

## Negatives sixteen and seventeen — and the first bone, which was false

**16. `weave_fill` / weave-relative topography.** Best-shaped candidate the
project produced; three independent measurements gave excess +0.111, +0.076,
+0.032 in the order taken. Monotone decline across fresh draws = selection on
the draw. Below the 0.09 bar. Precision lift x1.35 (9.5% of the top-5% pixels
are ink, against a 7.0% base rate).

**17. `specks` — THE FIRST BONE, and it was false.** Dog Cerberus cleared every
gate at 20:35: AUC 0.783 vs null 0.660, excess +0.123, held on a confirmation
set it was never selected against, jitter 1.00, blind 0.565, blank 0.018.

Killed on both metrics:

| test | claimed | measured |
| --- | --- | --- |
| AUC, fresh draw A | 0.783 (excess +0.123) | 0.641 (excess **-0.032**) |
| AUC, fresh draw B | — | 0.626 (excess **-0.073**) |
| blind scroll AUC | 0.565 | **0.621** |
| correlation, fresh draw | — | +0.015, 0% significant |
| per-scroll | — | +0.015 / -0.027 / +0.020 — signs disagree |
| weight jitter | 1.00 | **0/10** |

Below its own spatial null on both fresh draws, and it fires harder on the
blind scroll than on the ink. The tell was in the alert all along:
`partial_r = 0.024` — it explains almost nothing beyond sheet brightness,
contrast, coherence and curvature, which is the exact confound profile this
project has killed candidates for since the first night.

**Process lesson:** the alert fired and nobody noticed for two hours because no
one was watching the directory. `BONE.md` instructed running `verify.py` and
that instruction sat unexecuted. An alert that nothing acts on is not a gate.
