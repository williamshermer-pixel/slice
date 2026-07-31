# The calibrated hunt of PHerc0139 — 2026-07-30

Searched *On Gods* (Philodemus, unread) for ink the published maps never
called. **No new letters.** The value here is that the negative is calibrated:
we measured what the instrument would have seen, and we killed our own best
candidates with a control rather than believing them.

## What was run

Five RunPod GPUs mapped 38 segments of PHerc0139, up to three aimed windows
each (text band 0.30 / text edge 0.12 / margin 0.04), using the tuned model —
`PHerc.1667-iteration-5` fine-tuned on this scribe's own called text
(`out/bootstrap/tuned_0139_honest.pt`, held-out AUC 0.944) — with the proven
renderer: depth band z27..z89, clip[0,200]/255, tile 256 / stride 64, Gaussian
logit blending. 77 raw sigmoid maps, `out/lostbook/`.

## The candidate that died, and how

The first pass (relative threshold: ours > p96 AND published < 60, his-hand
component gates) produced **three candidates** — letter-sized, correct advance
rhythm, adjacent to called text.

**All three died to a spatial null.** Rolling our own map by a large offset
preserves its histogram and autocorrelation exactly while destroying its
registration to the papyrus; **23 of 24 rolls reproduced the same
candidates** (p = 0.80, 0.28, 0.92). `tools/null_differential.py`.

Cause: a *relative* threshold selects the top 4% of pixels whether or not ink
exists. In a margin window that is simply the noisiest 4%.

> **This also indicts the differential result of 2026-07-29** ("9 of 22
> segments carry letter-sized our-hot/theirs-cold structure; top w048, w059,
> w037, w038"). Same relative threshold, no null was run. **Withdrawn** unless
> re-tested under the machinery below.

## The instrument that replaced it

| step | measurement |
| --- | --- |
| our maps vs his published calls | **AUC 0.919–0.928** (36 text windows) |
| per-pixel floor at 0.2% blank FPR | 0.894 — recovers only **9.9%** (shape) / **12.4%** (envelope) of his known letters |
| letter-scale box mean (1.08 mm box) | **AUC 0.981** vs blank, **77.7%** detection at 0.1% FPR |
| **condition control** (null = blank sheet INSIDE the text block) | **AUC 0.961** vs 0.964 uncontrolled — letters median **0.462** vs same-condition blank **0.122** = **3.8×** |
| power, ≥2 detections | 87% at 3 hidden letters, **99% at 5**, 100% at 10 |

Three failures forced this design:

1. **Per-pixel thresholding is too blind at his hand.** A letter is thousands
   of pixels; the statistic must integrate over the letter, not trust any
   single pixel. Box-mean over his measured 1.09 mm letter took detection from
   ~10% to ~78%.
2. **Condition, not ink, is this project's standing failure mode** (text sits
   on well-preserved sheet; every historical false positive fired on
   preservation). Redrawing the null from blank sheet *inside* the text block —
   same sheet, same damage exposure — the AUC **held**. That is the first
   clean ink-vs-condition separation this campaign has produced.
3. **Model spillover manufactures candidates near text.** The model's response
   smears past a letter's called extent, so the hunt's null is restricted to
   blank boxes ≥2 letter-widths from ANY called pixel, matching the geometry
   candidates are allowed to occupy.

Also fixed on the way: the p96 mask went **silently empty** whenever >4% of a
map saturated (a search reporting confident silence on its hottest maps), and
published-map alignment assumed an 8× downsample where the true factor is
8.0006 — now measured per segment.

## Result

**78 windows across all 38 segments. One candidate. Zero survivors.**

The single candidate is worth naming because of where it sat: segment
`20260422000000-title` — the **title region**, the most valuable target on any
scroll (PHerc0172's title was read in May 2025). Two letter-scale clusters,
peak box-mean 0.382. It **died at the spatial null**: 13 of 24 rolled copies of
our own map produced as many clusters (p = 0.56). Honest, and the title region
deserves a dedicated pass at native resolution rather than one margin-aimed
window.

`out/lostbook/hunt.json`, evidence render `out/lostbook/evidence_hunt.png`.

The margins of *On Gods* are **quiet at this instrument's sensitivity** — and
the sensitivity is now a number (≈78% per letter, ≥99% power at five letters)
rather than a hope.

## What bounds this negative

- **Circularity.** The model was fine-tuned on this scroll's published calls,
  so it is biased *toward* agreeing with them. A search for what those maps
  missed inherits that bias. The honest ceiling on any discovery claim here.
- **"Known letters" are published-detector output, not human readings.** At
  1.09 mm neither the published map nor ours resolves letterforms — only
  letter-sized ink masses (visible in the evidence render's A2/A3). The
  positive control therefore proves agreement with a working detector at
  letter scale, not letterform reading.
- **Coverage** is up to three windows per segment, not whole segments.

## Where this leaves the campaign

The letter-scale + condition-controlled + spillover-safe + null-validated
detector is reusable and is the first honestly-powered ink search this project
has had. The obvious next application is the one the resolution argument
favours: **run it on a big-hand scroll** (Scroll 1's 3 mm hand, where our
renderer demonstrably draws letterforms, and 1667/0814 at their measured
hands). Every published map on every scroll was binarized the same way, so the
discarded band is the hunting ground everywhere — and now there is an
instrument that can search it without fooling itself.

## Reproduce

```bash
python3 tools/fleet_lostbook.py launch 5   # then upload / status / harvest / terminate
python3 tools/calibrate_floor.py           # absolute floor on his known ink
python3 tools/letterscale_0139.py          # letter-scale detector + power
python3 tools/condition_control_0139.py    # ink vs preservation — the control
python3 tools/hunt_0139.py                 # the search + mandatory spatial null
python3 tools/evidence_hunt.py             # the render for human eyes
python3 tools/test_differential.py         # gate calibration harness
```


## THE NIGHT OF FOUR SCROLLS — appended 2026-07-30 late

"Adapt and find ink" — the directive. Four scrolls searched with the
calibrated instrument in one night. No new ink. Every silence has a number.

| scroll | segs/windows | AUC vs pub | per-letter | control | hunt |
| --- | --- | --- | --- | --- | --- |
| PHerc0139 (tuned) | 38 / 78 | 0.92 | 78% | 0.96 | quiet |
| Scroll 1 | 50 / 37 | 0.80 | **98%** | **0.99** | quiet (5 cand., all null-dead) |
| PHerc0500P2 | 38 / 54 | 0.83 | 26–37% | 0.84 | quiet (5 cand., all null-dead) |
| PHerc0343P | 8 / 13 | 0.77 | 28% | 0.84 | quiet (1 cand., p=1.0) |

**The adaptation finding (new, publishable): fine-tune gains are
SEGMENTATION-BOUND.** Same recipe, same steps, same scribe-specific text:
+0.094 AUC on 0139's curated segments; **+0.011** on 0500P2's auto-debug
segments (`out/p0500p2_tuned/ab.json`). Training cannot rescue rough
flattening — the wall on auto-segmented scrolls is upstream geometry, not
model knowledge. Corollary: PHerc0814 (18/19 auto-grown) shares the wall.
0343P is curated but its text is too sparse to train on (max window cov 14%).

**The ruler correction:** letter heights from connected components of
binarized maps are 3–5× low (fragments, not letters). `tools/measure_hand.py`
(band FWHM) validates at 2.94 vs Scroll 1's known 3.00 mm. Validated hands:
Scroll 1 3.00 / 0500P2 1.92 / 0343P 1.67 / 1667 1.63 / **0139 1.61 (not
1.09)** / 0814 1.28. The library writes small; Scroll 1 is the outlier; and
everything but Scroll 1 sits between the model's 0.29 mm output grid and the
~2 mm shape-resolution line. That band is the game.

**Ops lessons banked:** zombie pods (check `runtime`, not status); PIL bomb
guard vs 200+ MP published maps; low aims land off-sheet; keep-out is a fixed
physical distance; DONE pods bill while sleeping — kill workers at harvest;
harvest must never refetch held files (a dead pod's failed fetch deleted 42
metas — reconstructed deterministically, 12/12 survivor-verified).

**Where new ink still lives, ranked:** (1) segmentation quality itself — the
auto-grown scrolls become searchable exactly when their flattening improves,
which is the field's bottleneck, not ours; (2) Scroll 1's 30 uncovered
segments + the 0139 title segment at native res; (3) 1667 margins (curated,
1.63 mm, field-read but never differential-searched); (4) bootstrap round 2
on 0139 with the honest recipe. All pods terminated; ~$20 total for the night.
