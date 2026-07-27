# What would count as finding letters

Written **before** any candidate result, deliberately. Once something exciting is
on screen it is too late to decide what counts — the criteria bend to fit the
picture. So they are fixed here, in advance, and dated.

Established 2026-07-27, during the session that produced the tooling in this
repo. Nothing in this document was written with a result in hand.

## Why this exists

Two failures already happened in that session, both mine:

- The fibre-orientation flip was called "confirmed" from a single tile. A
  six-tile sample gave a median of 57° with one tile at 3.6°. The claim was
  withdrawn.
- Letter stacking produced a correlation of +0.357 against the ink map and was
  reported as promising. A 200-draw permutation null gave **p = 0.365**. The
  effect was nothing.

Both were pattern-matching on noise while wanting a result. That is the default
failure mode here, not an unusual one, and it gets worse the longer a session
runs. Ink detection has a long history of people seeing letters in thresholded
noise; the field's own open-problems page warns about it.

The point of a pre-registered standard is to be argued with by a document rather
than by a tired person at 3am.

## The bar on Scroll 1 (where the answer is known)

PHerc. Paris 4 segment `20231005123336` has a **published ink detection**, and it
sits on exactly the level-3 grid of the surface volume. Any method must be shown
to work here first.

**A method passes only if:**

1. It reproduces the published ink at correlation **well above r ≈ 0.2**, which
   is the ceiling every hand-built feature reached in testing — texture,
   geometry, depth coherence and relief alike. Beating 0.2 slightly is not
   passing; it is landing in the same place by another route.
2. It is evaluated on a region it was **not tuned on**.
3. The comparison is against the ink map, not against an impression of it.

A method that cannot reproduce known letters where the answer exists does not
get to make claims where it does not.

## The bar on an unread scroll

All four, not a majority:

1. **Line periodicity.** Text sits on evenly spaced baselines. Scroll 1's hand
   measures a **6.18 mm** line pitch. Papyrus fibre is periodic at roughly
   **1 mm**. A candidate must show periodicity in the text band, in a window at
   least 2.5 line pitches tall — a shorter window cannot detect line spacing and
   will fail even on genuine text.
2. **Letterform repetition.** A scribe wrote each letter thousands of times. If
   shapes are found, the *same* shapes must recur. Structure that never repeats
   is not writing.
3. **Alphabet closure.** Recurring shapes must cluster to roughly **24** classes.
   Not 200, which is noise. Not 3, which is a texture artefact.
4. **Held-out region.** Whatever any parameter was chosen on, the result is
   demonstrated somewhere else.

## Standing rules

- **Null test, always.** Any correlation is reported with a permutation null.
  An effect that does not clear its null does not exist, however good it looks.
- **Negative control.** Run the method on a region known to have no ink. Real
  signal knows where letters are absent. A detector that lights up everywhere
  has found the papyrus, not the writing.
- **Multiple comparisons are real.** Anything that appears only after sweeping
  twenty variants is an artefact of the sweep. Count the variants and say so.
- **Ground truth is never an input.** Locations or shapes taken from the ink map
  may be used to *evaluate*, never to produce the thing being evaluated.
- **No generative models on the evidence.** No diffusion, no img2img, no
  inpainting, no upscaling of anything that will be read as a finding. A model
  that invents plausible detail will invent plausible Greek, confidently and
  unfalsifiably. Generative models may score hypotheses; they may never draw the
  image.
- **Publishing a negative is a result.** "Tested, failed, here is why" is worth
  more to this field than a maybe.

## The field's own bar

Stricter than the above and the one that actually pays: **10 legible letters
within a single 4 cm² area**, mesh in tifxyz with flattening, a
programmatically-generated image with no manual annotation, a 1 cm scale bar, no
overlap between training and prediction regions, and reproducible disclosed
methodology. See scrollprize.org/prizes.

## What is already known to be dead

Recorded so it is not rediscovered:

| tested | result |
| --- | --- |
| Density / attenuation | r = **+0.002**. 88% distribution overlap. Carbon on carbon. |
| Raking light on relief | r = 0.02. Differentiates away the signal it needs. |
| Frequency notch | Weave and stroke share a band — 335 µm vs 346 µm. |
| Orientation wedge | +0.016 over baseline. Real, negligible. |
| Letter stacking (√N) | **p = 0.365.** Interference is spatially correlated, so averaging does not converge. |
| Crack-network geometry | \|d\| < 0.08, below the brightness control. |

And the constraint behind all of it: the ink layer is ~15 µm. At the unread
scrolls' 8.64 µm sampling that is **1.7 voxels**, under the ~3 needed to resolve
a feature at all. The ink is not faint on those scans. It is under-sampled.
Scroll 1 gets 6.2 voxels through the same layer, which is why it could be read.
