# THE READER — design v1 (Fable, 2026-07-29)

Turns calibrated ink-probability maps into RANKED LETTER HYPOTHESES with
calibrated confidence. Never generates; only scores. Built to survive the
specific failures this project has already measured.

## The two measured constraints that shape everything

1. **Correlated noise kills naive matched filtering.** Measured twice:
   letter-stacking p=0.365; template matching median gain −0.046
   (correlation lengths 13–45 px, so letter-area integration doesn't buy
   √N). CONSEQUENCE: never score a template by raw pixel correlation
   against the field. Score it by **likelihood-ratio against a local null
   ensemble**: corr(template, patch) compared to the distribution of
   corr(template, shifted/rotated patches from the SAME neighbourhood).
   The neighbourhood null absorbs the correlated background; only
   letter-specific structure survives. Every score in the reader is a
   percentile against its own local null, never a raw number.

2. **Sub-resolution hands (0139) cannot be read at map level.**
   CONSEQUENCE: the reader has two modes.
   - **Shape mode** (hands ≥ ~2 mm: Scroll 1, 1667, 0814): full letterform
     scoring as below.
   - **Envelope mode** (small hands): score only what survives blur —
     letter presence, advance rhythm, word-gap statistics — and hand the
     candidate to the regenerator/native pipeline rather than pretending
     to classify it.

## Pipeline (shape mode)

```
map (raw sigmoid, fixed renderer, defogged copy for display only)
  → grid fit: line pitch + baseline via row-autocorr (per-scroll hand)
  → slot proposal: letter-advance combs along each baseline
  → per-slot template bank scoring (24 capitals, PER SCRIBE, harvested
    from transcription-aligned called text; augment ±10% scale, ±8° rot)
  → local-null percentile per (slot, letter)
  → Greek prior: character 5-gram (First1KGreek + Diorisis; TLG excluded)
    via beam search over slot lattices; scriptio continua — the LM also
    segments words
  → output: per slot, top-3 letters with (image percentile, LM boost,
    joint score); UNCALLED below threshold — silence is an output
```

## Calibration harness (build FIRST — the reader is not trusted until this passes)

- Take transcribed regions (1667 end-to-end text; Scroll 1 GP columns).
- Hide the transcription; decode blind from OUR maps; grade letter
  accuracy vs the scholars.
- Report: accuracy vs image-percentile curve → the CONFIDENCE CALIBRATION
  ("when the reader says 80%, it is right N% of the time").
- Also run on SHUFFLED templates (wrong alphabet) — must collapse to
  chance; if it doesn't, the harness leaks.
- William's Ν-vs-Μ bet (HANDOFF) is graded in this harness.

## Hallucination posture (non-negotiable, from the field's own stance)

LM never proposes marks; it only re-ranks image-proposed candidates.
Every reported letter carries its image evidence separately from its LM
boost. Renders ship raw-beside-defogged. The deliverable to papyrologists
is a RANKED SUGGESTION SHEET, never a transcription.

## Template bank (per William's doctrine)

Real specimens only, per scribe: transcription-aligned crops from called
text (labels = scholars' letters), fragment IR photos when the data-server
registration lands, GP columns for Scroll 1. Font glyphs are permitted
ONLY as a cold-start prior, flagged as such, and retired per scroll as
real specimens accumulate. No cross-scribe transfer without a measured
transfer test.

## Implementation notes for the build (Opus can take it from here)

- Reuse: hand-measurement code (letters/pitch), fleet maps in out/book/,
  fixed renderer for fresh maps, aim/window machinery.
- Transcription→map alignment is the only new hard sub-problem: start
  with 1667 (paper's plates name columns/lines); align by matching the
  called-component pattern of a column against the transcription's line
  lengths (dynamic programming over line-break positions), verify by eye
  on one column before scaling.
- Everything CPU. No pods needed until maps must be regenerated.
- First milestone: calibration curve on ONE 1667 column. Nothing else
  gets built until that curve exists and the shuffled-alphabet control
  collapses.
