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
