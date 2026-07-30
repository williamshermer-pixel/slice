# What the ink actually IS, and why fourteen mechanisms failed

Researched 2026-07-27. This is the document that should have existed before any
detector was written. Every mechanism in this project was designed against an
assumption about the ink that turns out to be wrong.

## The assumption we were working from

"Ink is a ~15 µm carbon layer lying on the sheet face. Find it by density,
texture, or relief."

Two of those three are the wrong physics.

## What the literature establishes

### 1. The ink is not pure carbon — it contains lead

Brun et al., *PNAS* 113:3751 (2016), "Revealing metallic ink in Herculaneum
papyri": lead is present in the ink at **84 ± 5 µg/cm²**, a concentration the
authors argue is too high to be contamination and was therefore deliberate.
Follow-up work (Tack et al., *Sci. Rep.* 6:20763) quantified and speciated it.

Worked through: 84 µg/cm² spread through a 15 µm layer is 0.056 g/cm³ of lead,
against metallic lead at 11.34 g/cm³ — about **0.5% by volume**. Lead's mass
attenuation coefficient near 50–60 keV is roughly 30× carbon's.

**Consequence:** if the lead were uniformly distributed the layer would be
several times more attenuating than the papyrus and trivially visible. It is
not visible (measured density correlation r = +0.002, 88% distribution
overlap). Therefore the lead is **particulate**, and the signal lives in the
extreme upper tail of the voxel distribution — which every box filter, band
mean and PCA in this project averages away.

Note also that lead XRF is what makes the letters legible in the synchrotron
work. We have attenuation only, not fluorescence.

### 2. The working mechanism is PHASE CONTRAST, not absorption

This is the big one.

> "X-Ray Phase Contrast Tomography is sensitive to materials with similar
> characteristics, as in the case of the carbon-based ink and the carbonised
> surface of the papyri (both of which exhibit weak levels of absorption)."

And, decisively:

> **"The carbon black ink does not completely penetrate the fibres, causing the
> X-rays to undergo a minimum deviation at that point. This edge enhancement
> effect is crucial for distinguishing the ink from the papyrus surface."**

(Mocella et al., *Nat. Commun.* 6:5895, "Revealing letters in rolled Herculaneum
papyri by X-ray phase-contrast imaging", and the 2016 follow-up.)

**Consequence:** the ink is detectable because it sits ON the fibres without
soaking in, creating a refractive-index discontinuity. What a detector should
look for is an **edge fringe** — the antisymmetric bright/dark doublet that
phase contrast produces at a boundary — not an intensity level and not a mean
density difference.

Every one of our fourteen mechanisms measured a *level* (density, brightness,
relief height, local variance, orientation coherence). None measured a
*fringe*. That is a structural blind spot, not bad luck.

### 3. The visible signature is "crackle" — texture plus relief

From the Vesuvius Challenge's own tutorial:

> "In PHerc. Paris 4 in particular, ink can sit as a thin layer on the papyrus
> surface, and on the flattened surface volume it often shows up as a crackle —
> a texture like cracked mud, raised slightly above the papyrus."

Two things to note. It is **raised**, so relief is real — which is why the 2025
topography work below succeeds. And it is called out **"in PHerc. Paris 4 in
particular"**, which is a warning that the signature may not transfer across
scrolls. Our own condition survey found correlation length varying 7.3× and
contrast 2.9× between scrolls, which is consistent with that.

### 4. Surface topography alone carries enough signal — at high resolution

*Ink detection from surface topography of the Herculaneum papyri*, **Sci. Rep.**
(2026), s41598-026-58467-1: a deep-learning model trained on 3D optical
profilometry of mechanically opened papyri shows that **surface morphology alone
distinguishes ink from papyrus**.

This vindicates the RTI/relief line of attack in principle. It also explains why
ours failed: optical profilometry resolves nanometres of height; our height
field is derived from an 8-bit CT volume with a measured noise floor of
~1.2–2.2 µm.

### 5. The resolution requirement

Reported minimum voxel size to detect carbon ink in micro-CT: **3–12 µm,
probably nearer 3**, with ink-indicating surface patterns detectable at **4–8 µm
resolution and 16 bits of density per voxel**.

## The measurement that follows from this — and it is ours

**Every surface volume in the public bucket is 8-bit.** Verified directly:

| scroll | dtype | µm/voxel (CORRECTED) |
| --- | --- | --- |
| PHerc0139 | `\|u1` | 2.258 |
| PHerc0172 | `\|u1` | 7.910 |
| PHerc0343P | `\|u1` | 2.215 |
| PHerc0500P2 | `\|u1` | 2.215 |
| PHerc0814 | `\|u1` | 2.258 |
| PHerc1667 | `\|u1` | 2.258 |
| PHercParis4 | `\|u1` | 2.258 |

**The µm column above was WRONG until 2026-07-27** and read 1.129 for four
scrolls. That figure was parsed from the filename and is the ORIGINAL SCAN
resolution; the array we read is level 0, whose OME scale is 2.258 — exactly
2× coarser. See `data-capabilities.md`. Voxels through a 15 µm ink layer are
therefore **6.2–6.8 across all resolvable scrolls**, not 13.3, and PHerc0172
remains the only blind scroll at 1.9.

Resolution is fine — most are well inside the 3–12 µm requirement. **Bit depth
is not.** If 16 bits of density are needed and the public volumes carry 8, then
the ink contrast may sit below one quantisation step, and no amount of cleverness
applied to these arrays recovers it.

**Status: the 8-bit fact is measured and certain. The bit-depth EXPLANATION is
measured and largely REJECTED.**

Quantisation audit, 8 held-out tiles, non-air voxels in the sheet band:

| scroll | p2 | p98 | distinct levels | effective bits |
| --- | --- | --- | --- | --- |
| PHercParis4 | 42 | 142 | 101 | 6.66 |
| PHerc0500P2 | 44 | 149 | 106 | 6.73 |
| PHercParis4 | 8 | 183 | 176 | 7.46 |
| PHercParis4 | 28 | 159 | 132 | 7.04 |
| PHerc0500P2 | 48 | 140 | 97 | 6.60 |

Pooled: 254 of 256 levels used, sheet contrast 104 grey levels. A sheet
occupies ~100 distinct levels — 6.6 to 7.5 effective bits. The data uses its
range properly and is NOT crushed into a handful of steps.

So an ink contrast of even 2–3 grey levels would be representable. Quantisation
is not the barrier it looked like, and the honest conclusion moves elsewhere:
**the data plausibly contains the signal, and our linear-correlation readout is
too weak to extract it.** That is consistent with the positive control, which
showed the readout needs ~34% of sheet contrast to reach r=0.25, and with CNNs
succeeding on comparable data.

Recorded because it was nearly written up as a headline finding on the strength
of one secondary-source sentence, and it does not survive ten minutes of
measurement.

## The weave-relative reframing — and the first well-shaped candidate

Mechanism 4 in this project was a frequency notch, and it died on the finding
that **weave and stroke share a band: 335 µm against 346 µm**. They are the same
scale, so no filter separates them.

That failure is actually the instruction. The weave and the ink differ in
STRUCTURE, not scale: the fibre lattice is periodic and locally oriented, a
stroke is not. So do not filter the weave out — model it, and measure the ink as
an ANOMALY against it. Physically, per the incomplete-penetration result, ink
should either **lift** a fibre crest or **fill** the gap between fibres.

Built as `tools/weave.py`. First results, 12 held-out tiles:

| feature | ink r | partial r | verified-blank | blind scroll |
| --- | --- | --- | --- | --- |
| `weave_amp` | +0.131 | 0.188 | 0.128 | 0.065 |
| **`weave_fill`** | **+0.135** | **0.252** | 0.128 | **0.036** |
| `weave_lift` | +0.031 | 0.038 | 0.116 | 0.046 |
| `weave_resid` | +0.041 | 0.121 | 0.103 | 0.019 |
| `weave_period` *(control)* | +0.104 | — | 0.197 | 0.113 |

**SUPERSEDED 2026-07-27.** The correlation-era figures in this table were never
converted to AUC and the candidate has since been re-measured three times, each
lower than the last (+0.111 -> +0.076 -> +0.032 excess). It sits below the 0.09
bar and is dead by this project's own criterion. See `spec-response.md`. The
reasoning below is kept because the physical argument still stands; the numbers
do not.

`weave_fill` was the first feature in this project with the right SHAPE of
evidence rather than the right headline number:

- its partial correlation is **higher than its raw** (0.135 → 0.252). Removing
  sheet brightness, contrast, coherence and curvature makes it stronger. Every
  confounded feature so far does the opposite.
- it is nearly silent on the **blind scroll** (0.036), where the ink was never
  sampled and no genuine detector should fire. `offaxis`, the previous best,
  scores 0.108 there.

It has not cleared any bar. Raw magnitude is low and blank is 0.128 against a
0.12 threshold. Its parameters were guessed, not searched, and are now in the
dogs' bank for proper optimisation. Two candidates have already died tonight
after looking better than this on the headline number, so it is recorded as a
direction, not a result.

`weave_period` is in the bank as a deliberate trap: it IS the papyrus
structure, and it scores +0.104 against ink. Any candidate that leans on it is
reading the weave.

## Is the lead visible in OUR scrolls? No — and the bound is ours to state

Worked from Brun's number: if the ink in these scrolls carried lead at
84 µg/cm² through a 15 µm layer, that is 0.056 g/cm³ of lead. Lead's mass
attenuation near 50–60 keV is ~30× carbon's, so the ink layer would be roughly
**5× more attenuating than the papyrus around it** — not subtle, not a
statistics problem, plainly visible in any slice.

Measured, 12 held-out tiles, ink vs bare papyrus in the depth band:

| test | median | mean ± SE |
| --- | --- | --- |
| absolute thresholds (>128 vs <40), raw | +0.334 sd | +0.437 ± 0.140 |
| same, high-passed at 0.7 mm | +0.248 sd | +0.226 ± 0.121 |
| **per-tile percentiles (top/bottom 20%), high-passed** | **+0.022 sd** | +0.117 ± 0.090 |
| **same test on the BLIND scroll** | **+0.069 sd** | +0.085 ± 0.036 |

The absolute-threshold version looked like a real discovery — a consistent
positive that survived high-passing to letter scale. It is an artefact of the
thresholds: >128 and <40 select different populations on tiles with different
exposure. Under a scale-free percentile split the effect collapses to +0.022,
which reconciles with the recorded density result of r = +0.002.

And the decisive comparison: **the blind scroll shows the same effect**
(difference +0.033 sd, SE 0.097, t = 0.34). PHerc0172's ink was never sampled
at 1.9 voxels, so whatever this is, it is not ink.

**Conclusion: these seven scrolls show no lead-driven attenuation contrast.**
Either their ink is not leaded at Brun's concentration, or the lead is
molecularly dispersed as a drying agent rather than particulate as a pigment —
Tack et al. leave both open, having ruled out contamination from solvent and
container. Consistent with this, the upper-tail `specks` feature finds nothing
(r = +0.003).

This is a reportable negative in its own right: a CT-derived upper bound on
lead content for the seven scrolls that carry published ink detections.

## The epistemic problem underneath everything

**The ground truth is a CNN's output, not ink.**

Every correlation in this project is against `ink-detection/downsampled/*.jpg`,
which is a model prediction. That has two consequences that no amount of
statistical rigour fixes:

1. A feature that correlates with the label may be reproducing what the MODEL
   keys on, including its confounds, rather than what ink is.
2. On the blind scroll the model emits mid-range values nearly everywhere —
   fewer than 50 confidently-blank pixels per tile, which is why an
   absolute-threshold test fails there outright. Those labels are the model
   guessing. Correlating with them measures nothing.

This does not invalidate the negatives: failing to match the labels means
failing to match a detector that demonstrably works. But it caps what a
positive would mean, and it should be stated plainly in any writeup.

## What to build next, in order

1. **Fringe detector.** Match the antisymmetric edge-doublet profile that phase
   contrast produces, at the fringe spacing implied by these scans. This is the
   mechanism the literature says actually works and the one thing we have never
   measured. Not a level — a signed doublet.
2. **Upper-tail particle hunt** (`tools/particles.py`, built). Lead is
   particulate; look for rare bright voxels and test whether they concentrate at
   the sheet face. The depth test uses no labels, so it cannot be a labelling
   artefact.
3. **Lower-tail porosity.** Ink wets and partially fills inter-fibre voids, so
   inked regions should be *less* porous. Opposite tail, same physical story,
   equally invisible to a mean.
4. **Quantisation audit.** Count distinct grey levels per sheet. Settles the
   bit-depth question empirically.

## The correction this forces on the writeup

"Fourteen mechanisms failed" is true but incomplete. The accurate statement is:

> Fourteen mechanisms that measure **levels** — density, brightness, relief
> height, local variance, orientation — all fail on 8-bit public surface
> volumes. The literature says the working signal is a phase-contrast **edge
> effect** from ink that does not fully penetrate the fibres, plus particulate
> lead. We never measured either.

That is a much more useful negative result, and it is honest about scope.

## Sources

- Brun et al., PNAS 113:3751 (2016) — https://www.pnas.org/doi/10.1073/pnas.1519958113
- Tack et al., Sci. Rep. 6:20763 — https://www.nature.com/articles/srep20763
- Mocella et al., Nat. Commun. 6:5895 — https://www.nature.com/articles/ncomms6895
- Ink detection from surface topography, Sci. Rep. (2026) — https://www.nature.com/articles/s41598-026-58467-1
- Vesuvius Challenge ink-detection tutorial — https://scrollprize.org/tutorial5
