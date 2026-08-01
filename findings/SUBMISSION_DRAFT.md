# Discord post (paste as `willsher` in #progress-prizes or the general channel)

Attach: `out/consensus/labels_PHerc0139_20250108000005.png`

```
Submitted for July: ready-to-run 3D ink label pairs for PHerc0139 (villa
#192), plus a cross-scan audit that uses the scroll's two published energies
(59 and 78 keV) to check any ink label on it.

We ran the audit on our own pairs first. It flagged 5 of 28, including one
"certified blank" pair that both maps call ink over 86.5% of. Scroll-wide, the
two published maps agree on about 59% of each other's calls, which seemed
worth knowing if you annotate over them.

Repo: https://github.com/williamshermer-pixel/slice
Viewer (no install): https://slice-site-alpha.vercel.app

The first version of the audit instrument was broken and adversarial review
caught it before submission. The failure catalog and the positive control that
now gates the pipeline are in findings/CROSSENERGY_1667.md. Happy to generate
label windows or audit runs on request.
```

# Issue comment for villa #192 (paste at github.com/ScrollPrize/villa/issues/192)

```
Shipped an attempt at this: 28 ready-to-run image/label pairs for PHerc0139,
plain zarr, 512-square tiles, depth recovered per pixel by sliding the ink
model's 62-layer window through the stack rather than projecting one image
across layers. Where the response profile is flat the label says
depth-ambiguous instead of guessing (12.7% of ink columns carry a resolved
depth; the rest ship as their own code). A QC gate rejects projected labels;
our own first version failed it.

On this issue's stated fear, labels teaching the surface rather than the ink:
each pair carries a condition-control AUC (ink vs blank sheet inside the same
text block, 0.96 curated), and, since PHerc0139 has published maps at both 59
and 78 keV, a cross-scan audit in each label's metadata. That audit flagged 5
of our own 28 pairs, including a negative pair both maps call ink over 86.5%
of, so the failure mode this issue names is real and measurable in ours too.

Repo: https://github.com/williamshermer-pixel/slice (samples/pairs has two
committed pairs; the set regenerates from the public bucket in one command.)
```

# Issue comment for villa #193 (paste at github.com/ScrollPrize/villa/issues/193)

```
One measurement from a label-generation attempt that may be useful here:
PHerc0139 has published ink maps at both 59 and 78 keV, and at a top-decile
call the two maps agree on 58.9% of each other's calls (median over 37
segments; Jaccard 0.417 against a density-preserving spatial null of 0.030).
Some of that gap is the known 1.1 vs 2.4 um resolution asymmetry and possibly
shared training lineage, but it bounds how far one map can serve as ground
truth for labels drawn over it, and the disagreement channel ranks where
re-annotation is worth the most.

Method, per-segment numbers, and the audit it enables (it flagged 5 of our own
28 label pairs) are in findings/CROSSENERGY_1667.md at
https://github.com/williamshermer-pixel/slice, generation tools included.
```
