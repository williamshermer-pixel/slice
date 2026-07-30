# Progress Prize submission — DRAFT v2 (2026-07-29)

For William to review. Deadline July 31, 11:59pm Pacific. Two parts: the
Discord post (what gets read) and the filing mechanics. Everything claimed
below is measured and reproducible from the repo; nothing is a reading.

## To file

1. `gh repo edit williamshermer-pixel/slice --visibility public`
2. Confirm LICENSE is MIT; README carries the summary below
3. Post in the Vesuvius Discord as `willsher`

## The Discord post

---

**Slice — a browser viewer for the scroll volumes, plus a field report:
one rendering bug you may also have, three calibration methods, and a
search nobody has run**

**The tool:** https://slice-site-alpha.vercel.app — no download, no login.
Streams OME-Zarr straight from the public bucket, client-side only.
Shareable URL coordinates, surface-volume depth scrubbing, letter-size
reference calibrated to the Scroll 1 hand. Repo (MIT):
https://github.com/williamshermer-pixel/slice

**1. The depth-band failure mode — check your pipeline for this one.**
Running `PHerc.1667-iteration-5` on a dense-text GP-segment window with a
blindly-centred 62-layer depth band scores AUC 0.654 and renders
letterless blobs. Sweeping the band start and re-scoring against the
published map: the ink band sits at **z27–z89** of the 116-layer L1
product, and the same window jumps to **AUC 0.944 with clearly drawn
letterforms**. A contact sheet in the repo shows letters appearing and
vanishing as the band slides. If your maps look like fog, check where
your window sits before changing anything else. (Also measured: 0139's
band peaks at the same z27; the sweep is cheap enough to run per scroll.)

**2. Per-scribe calibration matters more than it looks.** PHerc0139's
scribe writes **1.09 mm letters at 4.57 mm line pitch** — a third of
Scroll 1's hand (measured from 180 called components across 6 segments).
Letter-scale search gates tuned to Scroll 1 produce confident false
candidates on 0139; gates tuned to the measured hand retract them. We
fell for this in real time and the write-up documents the trap.

**3. A calibrated survey of an unread book's margins.** With the fixed
renderer (production spec: probability-space blending, 4-way TTA, Hann
window — replicated from villa/GP/title-prize source, recipe in repo),
we mapped margin windows of **22 PHerc0139 segments** and swept them
under the scribe's own hand: **quiet at this instrument's sensitivity**.
The raw sigmoid maps are preserved — which matters because:

**4. The differential search — cheap, and to our knowledge never run.**
Published ink maps are binarized (measured on 0139: p50=0, faint band
0.3–0.5% of pixels) — everything marginal was discarded at publication.
The band where *undiscovered* ink would whisper exists only in raw model
output. Searching **ours-confident ∩ published-empty** across our 22 raw
maps surfaces letter-sized, line-arranged structure on 9 segments —
which then FAILS letterform inspection at this scroll's tiny hand,
consistent with our measurement that a 1.09 mm hand sits below the
model's 0.29 mm output-block resolution. The method stands; on big-hand
scrolls (where the same renderer demonstrably draws letterforms) it is,
we believe, the cheapest untried new-ink search available. We are running
it on Scroll 1 next and the tooling is in the repo.

**Also in the repo:** eighteen earlier hand-crafted detection mechanisms,
all negative with measured causes and a spike-in sensitivity floor
(~34% of sheet contrast for linear readouts); a fully-controlled false
positive that survived spatial nulls, replication AND a physics control
and was killed only by rendering the evidence for human eyes; a
CT-derived no-lead bound on PHerc0172's public volumes; the finding that
native 1.129 µm surface volumes exist beside the `-L1` products for 17
segments; and a CPU-only reproduction recipe for the official model
(torch 2.2.2 + transformers 4.57.6, input scaled to [0,1] — 0–200 input
saturates it).

No letters were read. The tool says "too weak to call" when it is too
weak to call — that is the point of it.

---

## Notes for the edit pass

- Lead stays tool-first; the depth-band bug is the hook for practitioners.
- Keep every number as-is — all measured, all reproducible from the repo.
- Do NOT mention: prize amounts, the Zone saga by name, RunPod costs.
- Before posting: flip repo public, verify the fix contact sheet +
  before/after renders are committed under findings/ (no scroll data —
  maps derived from public data are fine, but keep them small).
