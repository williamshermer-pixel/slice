# BRIEF FOR FABLE — read this first, then `findings/`

Written 2026-07-28 ~01:15 local, for a handover in ~3 hours. Your mandate is to
**improve everything**. This document exists so you do not spend your first hour
rediscovering what already failed.

Everything below is measured. Where a number was wrong and got corrected, both
values are shown, because the corrections are the most useful part of the file.

---

## 1. THE ONE-PARAGRAPH STATE

We are trying to detect ink in carbonised Herculaneum scroll CT, targeting a
Vesuvius Challenge Progress Prize. **Seventeen mechanisms have been tested and
all seventeen are dead.** One candidate cleared every automated gate and turned
out to be false. There is a live browser tool
(https://slice-site-alpha.vercel.app), a large validated tooling stack, and a
set of documented negatives that is genuinely publishable. **No submission has
been written.** Deadline discrepancy unresolved: `HANDOFF.md` says July 31,
`CLAUDE.md` says August 31.

**Nothing is running right now.** See §2.

---

## 2. THE MACHINE — READ THIS BEFORE PLANNING ANYTHING

**The laptop has rebooted three times in the last ~12 hours**, each time
silently killing the entire search and its `caffeinate` keep-awake. Hours of
compute lost each time. As of this writing:

```
dogs: 0    ensemble: 0    verify: 0    caffeinate: 0
load average 3.25 on 16 cores — idle
```

What we know:
- `caffeinate -i -s` prevents sleep but **nothing survives a restart**.
- The first crash also wiped `/private/tmp`, destroying a 5 GB tile cache. The
  cache now lives at `~/.ink-cache` (13 GB, 235 tiles) and survives reboots.
- Cause of the reboots is **unknown and uninvestigated**. This is the single
  biggest practical obstacle. Worth ten minutes of `log show --predicate
  'eventMessage contains "shutdown"'` before starting a long run.

Restart everything with:
```bash
cd ~/Desktop/InK/tools && ./run_pack.sh 10 12
```

**Resource honesty:** 12 dogs deliberately occupy 12 of 16 cores and make the
machine feel sluggish. William noticed. Options are fewer dogs or `nice -n 10`.
Nothing of ours was responsible for the slowdown he asked about — at that moment
we were at 0%; it was the Claude app (~38% across three helpers) and
WindowServer.

**No LaunchAgent has been installed.** If you want the pack to survive reboots,
that is the fix, and it needs William's consent since it changes system config.

---

## 3. WHAT IS TRUSTWORTHY (the instruments)

These took the whole session to get right. Do not weaken them.

| instrument | file | what it does |
| --- | --- | --- |
| Spatial-shift null | `pack.auc_vs_ink` | shifts the TARGET, preserving autocorrelation. **Pixel-permutation nulls are invalid here and return p=0.0000 on noise.** |
| Verified-blank control | `pack.find_negatives` + `crop_coverage` | controls checked on the crop ACTUALLY scored, ≤0.5% ink |
| Physics control | `pack.strata` | PHerc0172 is 7.91 µm/vox = 1.9 voxels through a 15 µm ink layer. Text present, **ink never sampled**. Anything firing there is not ink. |
| Nested validation | `dogs.run_dog` | rotating selection set + disjoint confirmation set |
| Falsification battery | `verify.py` | fresh draw, per-scroll, ablation, jitter, both controls |
| Scorecard | `scorecard.py` | stability (Jaccard across depths/jitters), precision-at-top-5%, evidence render |
| Detection floor | `positive_control.py` | spike-in recovery: **the pipeline needs ~34% of sheet contrast to reach r=0.25** |
| Domain auditor | `.claude/agents/scientist.md` | adversarial; already caught 5 real errors |

**The scientist agent is registered but was created mid-session so the roster
never picked him up.** He should be selectable by name for you. Use him on every
number. He caught, among others, a 2× scale error and a check whose baseline was
too easy.

---

## 4. THE ERROR CATALOGUE — ten ways this project has already fooled itself

Each of these passed unnoticed once. They are in `scientist.md` too.

1. **Voxel size parsed from the filename.** `1.129um-....zarr` is the ORIGINAL
   SCAN resolution. The array we read is level 0, whose OME scale is **2.258 µm**
   — exactly 2× — on four of seven scrolls. Every micron-specified filter radius
   was double the intended size. Fixed in `pack.true_um()`; targets patched.
   **Never parse a resolution from a filename.**
2. **A negative control that contained ink.** Controls were picked by whole-map
   coverage <2%, then scored through a function requiring 5–85% coverage *in the
   crop*. Every "fires on blank papyrus" verdict was computed on inky crops.
3. **Correlation as the readout.** Against a sparse binary target it saturates:
   synthetic ink at 100% of sheet contrast reached only r=0.484. Switched to AUC
   reported as **excess over the spatial null** (shifted targets score ~0.62
   here from autocorrelation alone).
4. **Selection on the validation set.** Hill-climbing against one fixed held-out
   draw for 5,759 variants produced a knife-edge winner at +0.392 that collapsed
   to +0.053 on a fresh draw.
5. **A check with a baseline too easy to fail.** Depth-coherence scored 0.970 vs
   a 0.276 shuffle — but the blind scroll scored 0.915. It measured smoothing.
6. **Unreachable bars.** A threshold no candidate can clear produces guaranteed
   silence and teaches nothing. Check achievability against measured controls.
7. **Durable state in `/private/tmp`.** macOS purged it on reboot.
8. **Module-scope `sys.argv` parsing.** Importing such a module under another
   tool's argv threw; a `try/except` silently dropped an entire feature bank and
   a run proceeded with 11 features instead of 19, reporting nothing wrong.
9. **An "optimisation" that was a pessimisation.** An early-abort screen was set
   at AUC<0.60 while the null is ~0.62, so nothing was ever aborted and the
   extra evaluations made the pack slower. Measured, not assumed. Now 0.64.
10. **Metric mismatch between search and battery.** The dogs were switched to
    AUC while `verify.py` still computed correlation, so a kill compared two
    different quantities. Both are AUC now.

---

## 5. WHAT I GOT WRONG THAT YOU SHOULD NOT INHERIT

**I told William that using the flattened 2D image was "the error".** Our own
709 AUC-era variants do not support that:

| | best excess | feature |
| --- | --- | --- |
| 2D only | **+0.208** | `weave_period` |
| mixed | +0.175 | `weave_amp+pca_c2+weave_resid` |
| 3D only | +0.123 | `specks` |

Nine of the top twelve single features are 2D. The depth-column bank I built
specifically to stop flattening scored +0.063 in its own screen. **I then
reweighted the search to spend 65% of draws on 3D/physics banks on the strength
of that framing — an allocation the measurements do not justify.** Rebalancing
toward measured performance is an open decision William has not ruled on.

Note the top scorer is `weave_period`, which I planted as a **trap**: it IS the
papyrus fibre structure. It beating everything is the cleanest statement of the
real problem — sheet structure predicts the label better than anything we have
that is actually about ink.

---

## 6. THE PHYSICS, ESTABLISHED FROM LITERATURE + OUR MEASUREMENTS

Full detail in `findings/ink-physics.md`.

- Carbon ink on carbonised papyrus: **no attenuation contrast** (r=+0.002, 88%
  distribution overlap). Density will never work.
- The working mechanism is **phase contrast**: "the carbon black ink does not
  completely penetrate the fibres, causing the X-rays to undergo a minimum
  deviation at that point" (Mocella, Nat. Commun. 6:5895). It is an EDGE effect
  at the ink/fibre boundary, not a level.
- Lead IS in some Herculaneum ink at ~84 µg/cm² (Brun, PNAS 113:3751;
  contamination ruled out by Tack, Sci. Rep. 6:20763). **But not in our seven
  scrolls** — we bounded it: ink/bare difference +0.022 sd, and the blind scroll
  shows the same (t=0.34).
- **Weave and stroke share a band: 335 µm vs 346 µm.** No filter separates them.
  The only viable framing is to model the lattice and measure the anomaly.
- Bit depth is NOT the barrier: sheets use ~100 distinct grey levels (6.6–7.5
  effective bits). Quantisation is fine; our readout was weak.

**The epistemic ceiling:** every label is a **CNN's output**, not ink. On the
blind scroll the published model emits mid-range values almost everywhere. A
feature matching those labels may be reproducing a model's confounds. Real
ground truth needs opened fragments with infrared — **all six fragments in this
bucket contain `photos/` and nothing else.** That data is on Kaggle/scrollprize.
**Acquiring it is arguably the highest-value unblocked move available.**

---

## 7. THE DATA — what it can and cannot do

Full detail in `findings/data-capabilities.md`.

- 45 samples, 14 with `segments/`. **Seven** have surface volumes + published
  ink detections (~240 flattened segments). `CLAUDE.md` still says only
  PHercParis4 has any — **that is stale**.
- **PHerc1447: 4 flattened segments, ZERO published ink detections.** The only
  place in the bucket where a working detector could say something nobody has
  already said. Nothing has been run there.
- Six samples have segments but no surface volumes — traced, not flattened.
  Flattening is GPU/VC3D work, out of scope for this repo.
- **RETRACTED:** an earlier sheet-geometry table claimed faces at −15..−9 and
  +6..+18 and thicknesses of 41–75 µm. The scientist showed the stacks contain
  **no air at all** (dimmest end = 0.74 of peak) and median profile FWHM is
  **162 µm**. Those "faces" were gradient extrema of an interior slab. Any depth
  targeting derived from them is withdrawn.

---

## 8. THE SEVENTEEN NEGATIVES

`findings/overnight2.md` has the full table with reasons. Headlines:

- density, raking light, frequency notch, orientation wedge, letter stacking,
  crack geometry, morphological roller, crackle-to-spec, RTI specular, depth
  PCA, letterform matched filtering, weave-relative topography, `specks`, nine
  depth-column profile features.
- **Letterform matched filtering LOSES signal** (median gain −0.046) because
  correlation lengths of 13–45 px mean letter instances are not independent —
  the 75,000-voxels-per-letter area argument never buys √N.
- **The one bone (`specks`, dog Cerberus)** cleared held-out AUC 0.783 vs null
  0.660, confirmation 0.723, jitter 1.00, blind 0.565, blank 0.018 — then scored
  **−0.032 and −0.073 excess on two fresh draws** and **0.621 on the blind
  scroll**. `out/dogs/BONE.md` is marked KILLED.

---

## 9. OPEN THREADS, RANKED — where I would put your first hours

1. **The kill audit was never finished.** I launched the scientist to audit
   whether our KILLS are correct — we have been harsh on positives and credulous
   about negatives, which is its own bias. **He was killed by the reboot before
   reporting.** The crux he was measuring: what is the draw-to-draw sd of
   AUC-excess at n≈12? If it is large, "+0.123 then −0.032" is consistent with a
   weak-but-real effect and several kills may be wrong. **Re-run this first.**
2. **The ensemble was never finished.** `tools/ensemble.py` — logistic
   regression over all 38 features, fitted on tune scrolls only, numpy-only
   (sklearn is not installed). Every search so far picks 1–3 features with grid
   weights; this is the first learned combination and the highest-probability
   path to a real bone. Also killed by the reboot before producing output.
3. **`offaxis` is an unexplained confound.** It correlates 0.370 with ink,
   partialling out brightness/contrast/coherence/curvature does NOT touch it
   (0.381), yet it fires 0.175 on verified-blank sheet. Whatever it keys on is
   real, strong, repeatable, and not ink. Identifying it is a well-posed
   question and would sharpen every control we have.
4. **Run something on PHerc1447** (§7) — the only unlabelled flattened scroll.
5. **Rebalance the feature draws** toward measured performance rather than my
   theory (§5). William has not ruled on this.
6. **Write the submission.** Seventeen documented negatives, a measured
   detection floor, the 1.7-voxel resolution finding, the broken-control
   discovery, and a live tool is a real Progress Prize entry. Nothing is posted.

---

## 10. STANDING RULES

- Never tune and test on the same data.
- Every correlation gets a **spatial** null.
- Verified-blank control AND blind-scroll control, both inside the objective.
- **No generative models on the evidence, ever.** The asset is a tool that says
  "too weak to call" and is believed.
- Publishing a negative is a result.
- Never commit scroll data (CC BY-NC 4.0).
- Check `voxels_through_ink = 15 / (µm per voxel) >= 3` before trusting any
  scroll's role in a split.

---

## 11. COMMANDS

```bash
cd ~/Desktop/InK/tools

./run_pack.sh 10 12              # relaunch pack + caffeinate (survives nothing but a reboot)
python3 dogs.py --scoreboard     # who is ahead, by name
python3 ensemble.py 8 12         # the unfinished learned combination
python3 verify.py <alert.md>     # falsification battery on a candidate
python3 scorecard.py <feature>   # full card incl. stability + precision lift
python3 column.py 12             # depth-profile screen
python3 positive_control.py 6    # detection floor
ls ../out/dogs/DOGS_ALERT.md ../out/dogs/BONE.md
```

The pack names its workers: Argos, Pliny, Livia, Cerberus, Juno, Rufus, Nero,
Vesta, Remus, Scipio, Bruta, Philo. **The winner gets a bone.** Nothing has
legitimately claimed it.
