# The science, end to end — what is known, what we measured, where letters come from

Written 2026-07-28. Part I is measured in this repo or established literature
already verified locally. Part II is the external state of the field
(web-verified 2026-07-28). Part III is the synthesis: the paths to letters,
ranked by physics.

---

## PART I — THE MEASURED CORE (ours, do not re-litigate)

### 1. The object

A Herculaneum scroll is carbonized papyrus: sheets ~162 µm thick (measured
median FWHM across 140 tiles; the published 41–75 µm figure was our analysis
window reproducing itself, not the sheet). The ink is a ~15 µm layer of carbon
black sitting ON the sheet face — Mocella's key physical fact is that it does
not fully penetrate the fibres. The scribe's hand on Scroll 1, measured off
real ink: 6.18 mm line pitch, 3.00 mm letter height, 1.86 mm letter advance,
0.35 mm stroke width.

### 2. What the public data actually is

- Seven scrolls with flattened surface volumes AND published ink detections;
  ~240 flattened segments total. All **8-bit** (6.6–7.5 effective bits in the
  sheet band — quantisation measured and REJECTED as the barrier).
- True level-0 resolution 2.215–2.258 µm/voxel for six scrolls (filenames lie
  by 2×; OME metadata is authoritative) → **6.2–6.8 voxels through the ink
  layer**. PHerc0172 is 7.91 µm/voxel = **1.9 voxels: its ink was never
  sampled**, making it a physics control — anything firing there is not
  reading ink.
- The surface volumes contain **no papyrus/air boundary** — the stack never
  reaches air, so "the sheet face" cannot be located by material ending, and
  every profile-shape result is about an interior iso-gradient surface, not
  the true face.
- **Every ink label we score against is a CNN's output**, not ink. Real ground
  truth (IR photos of physically opened fragments, WITH registered CT) exists
  only in the Kaggle/scrollprize fragment release — not in this bucket. This
  circularity caps what any local positive can mean.
- **PHerc1447: four flattened segments, zero published ink detections.** The
  only place in the bucket where a working detector could say something new.

### 3. What the ink is, physically

- Some Herculaneum inks carry lead (Brun et al. PNAS 2016: 84 µg/cm²) — but
  worked through, that concentration would make the layer ~5× more attenuating
  than papyrus, i.e. unmissable. Measured here: no attenuation contrast
  (density r = +0.002, 88% overlap; percentile-split test +0.022 sd, and the
  blind scroll shows the same number). **These seven scrolls have no
  lead-driven contrast — a CT-derived upper bound on their lead content, and a
  reportable negative.**
- The literature's working mechanism is **propagation phase contrast**: ink
  that sits on, not in, the fibres creates a refractive-index discontinuity —
  an antisymmetric bright/dark edge fringe, not a density level.
- The Challenge's own visible signature is **"crackle"** — cracked-mud texture
  raised slightly off the surface, called out "in PHerc. Paris 4 in
  particular" — a warning about cross-scroll transfer that our condition
  survey quantifies: correlation length varies 7.3×, contrast 2.9× across the
  seven scrolls. A single global detector is probably the wrong object.
- 2026 Sci. Rep. topography result: surface morphology ALONE separates ink
  from papyrus — on optical profilometry resolving nanometres of height. Our
  CT-derived height field has a measured noise floor of 1.2–2.2 µm against a
  9 µm signal. Right mechanism, wrong instrument.

### 4. Seventeen mechanisms, one autopsy

Every dead mechanism measured a **level** (density, brightness, relief,
variance, orientation) or a linear filter of one. The physics says the signal
is a **fringe** (edge doublet), **particulate** (upper-tail voxels), or
**morphological** (crackle texture at sub-2 µm height scales). We then built
the physics-informed banks — fringe doublet (`scent`), particle hunt
(`specks`/`voids`), weave-anomaly (`weave`), per-pixel profile shape
(`column`) — and they died too, all below the 0.09 AUC-excess bar with the
controls in place.

The instrument-level explanation, from our own positive control (spike-in
recovery): **a linear correlation/AUC readout of any single hand-crafted map
needs ~34% of sheet contrast to register.** Injected ink at 100% of sheet
contrast only reaches r = 0.484 — the meter saturates. Measured real contrast
is ~0. The entire class was excluded by its readout, not by any one feature's
failure.

Two structural blockers, measured twice each:
- **Interference is spatially correlated** (correlation lengths 13–45 px), so
  letter-area integration does not buy √N. Matched letterform filtering makes
  signal WORSE (median gain −0.046). Any pixel-level stacking argument dies
  here.
- **Papyrus condition confounds everything.** Text sits on well-preserved
  sheet, so condition detectors masquerade as ink detectors. Cure:
  verified-blank controls chosen on the scored crop + the blind-scroll physics
  control, both inside the search objective.

And two method findings that generalize beyond this project:
- Selection on a fixed validation draw manufactures winners (~5,700 variants
  → a +0.392 candidate that collapses to +0.053 on a fresh draw, 0/10 under
  weight jitter). Rotating selection sets + disjoint confirmation sets +
  jitter-as-precondition are the cure.
- A negative control must be verified **on the crop it scores** — whole-map
  coverage lied to us for a full run.

### 5. Why CNNs succeed where all of this fails

The published detections exist, so the signal is in the data. What a CNN has
that our instrument class does not: nonlinear composition over a large 3D
context window, trained against labels — it can represent "crackle texture
near stroke-scale continuity in this depth band under this condition regime,"
which is a conjunction no single hand-crafted map plus linear readout can
express. Our floor measurement makes this quantitative: the per-map SNR is
below the linear-readout threshold, and the CNN is doing the integration we
proved √N-stacking cannot do naively (it learns the correlation structure
instead of assuming independence).

---

## PART II — THE FIELD (web-verified 2026-07-28)

### A. The winning lineage, 2023 → 2026

- **2023 Grand Prize** (Farritor/Nader/Schilliger): ensemble of TimeSformer +
  ResNet3D-101 + I3D over the flattened surface volume — **64×64 px in-plane,
  64 slices deep**, at 7.91 µm scan resolution. Strongest output was the
  TimeSformer. Code and weights public
  (github.com/younader/Vesuvius-Grandprize-Winner).
- **Ground truth was bootstrapped, not given.** Handmer spots crackle (Aug
  2023) → Farritor trains a small model on hand-labelled crackle → first word
  (πορφύρας) → Nader confirms via domain transfer + unsupervised pretraining →
  **~15 iterations of pseudo-label expansion**, with an ignore-mask excluding
  low-confidence pixels from the next round's loss. The labels our project
  scores against are the *product of this loop* — self-training output, which
  is exactly why they are circular for our purposes.
- **PHerc. 172 (Oxford):** words read Feb 2025 (διατροπή, φοβ-, βίου);
  **title read May 2025 — "Philodemus, On Vices, Book 1(?)"** (Roth & Nowak,
  $60k, MiniUNETR 3D architecture). Researchers' stated hypothesis: this
  scroll's ink shows **unusually strong X-ray contrast, possibly a denser
  contaminant like lead** (hypothesis, not confirmed).
- **PHerc. 1667: the first scroll read end-to-end** — announced June 25,
  2026, scanned at ESRF BM18, with a preprint ("Complete virtual unwrapping
  and reading of a rolled Herculaneum papyrus"). The field's current
  headline.
- Ink has now surfaced on **9 of 45 scanned scrolls/fragments**. Scroll 1's
  title region shows *no detectable ink* under current methods — that $50k
  Title Prize is open explicitly because it may need a new method.
- **Current canonical model:** `ink_canonical_2um` (2.4 µm) in the official
  ScrollPrize/villa monorepo. Best-practice scanning is now 2.4 µm isotropic
  at BM18 — the same scale as our surface volumes (2.215–2.258 µm).
- **The bottleneck, per the organizers' own 2026 Open Problems doc:**
  segmentation and *label quality*, not ink detection — "label quality is now
  one of the main unwrapping bottlenecks," and August 2026 progress money
  went almost entirely to segmentation/mesh tooling. They also state plainly
  that on most scrolls predictions "plateau or show little convincing ink"
  and **they do not know which pipeline stage is at fault** — scan signal,
  surface localization, label misalignment, architecture, or genuinely
  different ink chemistry per scroll. Cross-scroll generalization is the
  named biggest open problem in ink detection.
- Compute: official tutorial quotes ~1.5 h on one H100 for training; no
  published CPU-only inference benchmark exists either way. A single
  64×256×256 patch forward pass is small; CPU inference per-tile is plausible
  but unproven in public sources.

### ⚠ B. What this does to OUR physics control — flagged before anything else

Our blind-scroll control assumed: 15 µm ink ÷ 7.91 µm/voxel = 1.9 voxels →
ink never sampled → any correlation on PHerc0172 is not ink. **That argument
silently assumes weak contrast.** The community read the *title* of this
scroll. If 172's ink is anomalously attenuating (their lead-contaminant
hypothesis), a 15 µm bright layer inside a coarse voxel still shifts that
voxel's mean — partial volume does not erase strong contrast, it dilutes it.
Two possibilities, both consequential:

1. Their hypothesis is right → our "physics control" penalizes real ink
   response on 172, and every candidate gated on `blind AUC ≤ 0.58` was
   partly gated on suppressing genuine signal. The dogs' persistent blind
   AUCs of 0.54–0.62 may not have been pure confound.
2. Our measurement is right (we found NO anomalous attenuation on 172 —
   percentile-split test, +0.069 sd) → their lead hypothesis fails for the
   surface volumes we read, and that is a publishable check on a stated
   community hypothesis.

Either branch is a finding. Reconciling them (our depth windows never reach
the true sheet faces — see Part I §2 — so our lead test may have missed the
layer) is now a top-priority measurement, cheap, and ours to make.

**MEASURED 2026-07-28 (`tools/lead_sweep.py`, `findings/lead_sweep.json`) —
the control STANDS.** Depth-resolved sweep of every layer of the full
uncropped stacks, ink-vs-bare in SD units by scale-free percentile split,
rolled-label spatial nulls, 8 tiles per group: PHerc0172 is **flat at every
depth** — high-passed max excursion beyond the null envelope +0.000 sd
(curve never exceeds +0.064), raw +0.044. The layer cannot have been missed:
the whole stack was swept. So there is **no lead-driven attenuation contrast
in the public 7.91 µm PHerc0172 surface volumes at any depth** — the
blind-scroll physics control survives for this data product, and the
community's strong-contrast hypothesis, if true, is expressed only in scans
we do not hold (e.g. the 3.24 µm Diamond scan). This is a direct, publishable
check on a stated community hypothesis. Secondary note: PHerc0500P2 shows a
raw excursion (+0.50 sd at +40 µm from the interior peak) but the 2-tile
blank sanity group shows comparable small-n artifacts (+0.38 raw / +0.14 hp),
so nothing is claimed there without more tiles.

One partial rescue for the control: PHerc. 172 was **also scanned in its
entirety at 3.24 µm** (Diamond I12 module 3). The community's readings most
plausibly derive from that scan, not the 7.91 µm surface volumes in our
bucket — in which case "the 7.91 µm data never sampled weak-contrast ink"
can survive even though the scroll was read. But the strong-contrast (lead)
hypothesis, if true, breaks it regardless of scan. Both facts belong in any
writeup of the control.

### C. The ink signal, per the literature (confirming and extending Part I §3)

- **Attenuation is dead on arrival** for carbon-on-carbon; the organizers say
  it plainly. Lead is real but fragment-specific (84 and 16 µg/cm² on two
  PHerc.Paris.1 fragments; intentional, likely a drying agent) — "some
  fragments have lead, most scrolls read without it" is the accurate state.
- **The working physics is interface refraction**: propagation phase contrast
  produces Fresnel edge fringes where refractive index jumps — the ink layer
  sitting ON the fibres is such a jump (Mocella 2015). The signal is an edge
  effect, never a bulk level. (Our fringe detector was the right idea; see
  Part III for why it still failed here.)
- **Crackle, quantified** (Handmer's own post): lighter convex patches
  0.1–0.5 mm across, separated by narrow dark channels meeting at 60–90°,
  running straight for 2–4 mm at 0.5–1 mm width, sitting proud of the
  surface — observed at 8 µm pixels on Scroll 1. His causal mechanism is
  explicitly hedged (evaporative mineral concentration vs. contact artifact).
  The organizers' current formulation: models key on **texture/morphology +
  local phase shifts + their interactions**, and most scrolls show nothing as
  legible as Scroll 1's crackle.
- **The 2026 topography paper closes the loop**: a model on 3D optical
  profilometry of opened fragments reads ink from surface shape ALONE — the
  crackle is physically real, not a CT artifact. Profilometry resolves
  nanometre height; our CT height noise floor is 1.2–2.2 µm. Right mechanism,
  instrument three orders of magnitude too coarse.

### D. THE RESOLUTION FACT THAT REFRAMES OUR NEGATIVES

The organizers have published a direct comparison: **text legible at 1.1 µm
is partially lost at 2.4 µm.** Our working surface volumes are 2.215–2.258 µm
at level 0 — and for four scrolls that level 0 is a **2× downsample of a
1.129 µm original scan** (the filename resolution). We ran seventeen
mechanisms at precisely the resolution the field documents as
partially-destroying legibility.

**RESOLVED 2026-07-28 (bucket audit, verified against live .zattrs): the
native data is PUBLIC.** The `-L1` suffix on the zarrs we read means what it
looks like — a level-1 product tier. Findings:

- **17 segments publish a native `[1.129,1.129,1.129]` surface-volume zarr**
  beside the `-L1` one: 8 on PHerc0814, 8 on PHerc1667, 1 on PHerc0139
  (e.g. `PHerc0814/segments/20250925161630-auto_grown_.../surface-volumes/`
  `1.129um-0.22m-59keV-volume-20260521123630.zarr`, canvas 157240×42700 —
  exactly 2× the `-L1` sibling).
- **Scroll 1 (PHercParis4): none of its 81 segments has a native surface
  volume** — but its native RAW volume is public
  (`PHercParis4/volumes/20260608103018-1.129um-0.2m-78keV-masked.zarr`,
  59969×36006×32354), and each segment's mesh coordinates
  (`mesh/*.tifxyz/{x,y,z}.tif`) are published — so native surface volumes
  for Scroll 1 can be REGENERATED locally by resampling the mesh against the
  native raw zarr. That is a community-useful tool in itself.
- Native 1.129 µm raw volumes exist for every sample checked.
- dl.ash2txt.org answers anonymously but the documented path is
  registration; its license restricts disclosure of hidden-text findings
  outside official channels.

**Consequence: every physics-informed negative (fringe, RTI relief,
crackle-scale texture, height maps with their 1.2–2.2 µm noise floor)
deserves one re-run at native resolution on those 17 segments — 13.3 voxels
through the ink instead of 6.6, and a height field built from 2× finer
sampling — before it is final.** `pack.py` needs one change: prefer the
non-`-L1` zarr when a segment has one. Also noted: a region of PHerc0500P2
was scanned at **0.55 µm** — sub-micron truth may exist for one scroll.

---

### E. The Greek lane — verified open, with a named enemy

- **Nobody has chained ink-probability maps to a Greek language prior for
  Herculaneum.** Casey Handmer proposed *exactly this* in Nov 2023 — "the
  posterior probability of detecting ink where a character, word, or sentence
  implies it must be is higher than the prior probability" — as speculation.
  No implementation has been published since. Open territory, confirmed.
- **And the field's best team engineered it OUT.** The PHerc. 1667 paper
  states: "No OCR or language model was used at inference time or in the
  generation of pseudo-labels" — deliberately, to prevent "full-letterform
  hallucinations from linguistic or word-level priors." Reading was done by
  eight human papyrologists on enhanced renders. The Challenge FAQ flags
  letterform-model hallucination as a reviewed risk; Grand Prize rules
  require images be direct programmatic outputs of CT data and discourage
  ML windows over 0.5×0.5 mm.
- **Consequence:** a reader submitted as *evidence* will be rejected on
  principle. A reader submitted as a **calibrated hypothesis ranker** — the
  LM never generates, only rescores image-derived likelihoods; every call
  ships with its image evidence, its prior contribution separated, and a
  published calibration curve validated on held-out transcribed text — is
  the version Handmer's argument licenses and the 1667 team's objection does
  not touch. The papyrologists stay the readers; the tool ranks where they
  look. That framing is the whole ballgame.
- **Parts available:** Ithaca (Apache-2.0, public checkpoint, upgraded to the
  Aeneas architecture July 2025); a Llama-3 papyrology fine-tune
  (arXiv 2409.13870, open weights); First1KGreek (CC-BY-SA), Diorisis (10.2M
  words, tagged), DDbDP/DCLP on papyri.info (CC-BY, EpiDoc XML) — which now
  holds **nearly all Herculaneum texts in searchable form**, i.e. the
  validation ground truth for a reader already exists as machine-readable
  transcriptions. TLG stays out (license forecloses training use).
- Context for targets: PHerc. 139 was just identified as a previously
  unknown book of Philodemus' *On Gods*; PHerc. 1667 read end-to-end. Both
  are scrolls whose surface volumes we already stream and score.

---

## PART III — THE PATHS TO LETTERS, RANKED (final)

The three sweeps + our measurements force this order:

**0. Two cheap measurements that reframe everything we already did (days):**
   (a) Does 1.129 µm surface-volume data exist anywhere public (villa data
   server, non-S3 mirrors)? Our negatives were all run at 2.258 µm — the
   resolution the field documents as partially destroying legibility. If
   native-res data exists, the seventeen negatives get one re-run before
   they're final. (b) Re-run the lead/attenuation test on PHerc0172 at the
   true sheet faces (our windows never reached them) — it adjudicates the
   community's stated lead hypothesis AND the validity of our own physics
   control. Either outcome is publishable.

**1. The reader (weeks, CPU-only, open territory).** Grid fitter at the
   measured hand → letterform likelihoods from image evidence → Greek
   character prior (n-gram from First1KGreek/Diorisis first, Ithaca rescoring
   later) → beam search over scriptio continua → **calibration harness on
   DCLP transcriptions with letters held out.** Deliverable is the
   calibration curve, not a reading. It consumes the community's CNN maps,
   so it rides every future segmentation and dodges our resolution ceiling,
   the correlated-noise wall, and the GPU limit. Hallucination posture:
   ranker, never generator — see Part II-E.

**2. PHerc1447 first predictions (one overnight, if CPU inference holds).**
   Run the canonical open ink model (villa `ink_canonical_2um` / GP
   TimeSformer weights) on the four flattened, never-predicted segments.
   No public CPU-inference benchmark exists either way — so the run is
   double-barrelled: first ink predictions for a virgin scroll, plus the
   first documented CPU-only inference path for the canonical model (a
   Progress Prize-shaped tool in itself).

**3. Real ground truth (download-sized).** The Kaggle fragment release
   (CT + registered IR of physically opened fragments) is the only escape
   from CNN-label circularity, flagged in spec-response.md as the
   highest-value unblocked acquisition. Needed before any reader claim can
   be graded against something that is not itself a model output.

**4. Nonlinear combiner over the 38-feature bank (one night, low prior).**
   GBM/logistic on CPU — the last untried rung between linear readouts and
   CNNs. The floor measurement predicts it fails; it is cheap to be wrong.

**5. Segmentation (out of scope, but it is the war).** The organizers say
   label quality and surface tracing are the bottleneck; August 2026 prize
   money went almost entirely to segmentation tooling. Our viewer is already
   a segmentation-adjacent QC tool — that is the current prize-winning
   category, worth knowing when writing the submission.
