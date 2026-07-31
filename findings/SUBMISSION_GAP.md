# SUBMISSION GAP — read before rewriting v4

Written 2026-07-30 night, from the verbatim text of ScrollPrize/villa #192 and #193
against `SUBMISSION_DRAFT.md` v3. Deadline: **July 31, 23:59 PT**.

William's read is correct. v3 claims to answer #192/#193 and does not. Three
concrete mismatches, each quoted.

---

## Gap 1 — #192 asks for TRUE 3D. We ship a band.

**They wrote:** "in true 3d rather than a single image projected across multiple
layers."

**We wrote:** "Labels are nonzero only in the measured ink band (z27..z89 of the
116-layer stacks)… Voxel-level depth attribution is NOT claimed."

A constant band across z *is* a single image projected across multiple layers. That
is the precise thing the issue says it does not want. Our honesty about it is good;
it does not make it a fit. **We are declining the central ask in the body of the
submission that claims to answer it.**

## Gap 2 — #192 asks for ready-to-run PAIRS. We ship half a pair plus a script.

**They wrote:** "Image/label pairs of high quality 3d ink labels that are
'ready-to-run', no additional cropping or preprocessing required."

**We wrote:** labels in `label/` + `conf/`, and `tools/fetch_pair.py` "assembles the
image half from the bucket (CC BY-NC never redistributed)."

Running a fetch script to assemble the image half is, by definition, additional
preprocessing. **We ship labels, not pairs.**

→ **DECISION NEEDED:** CC BY-NC permits non-commercial redistribution with
attribution. If the data licence genuinely allows it, bundling the image half turns
this from a miss into a direct hit, and it is the cheapest win available. **Verify
the actual licence terms on the source volumes before deciding.** If redistribution
is barred, say so explicitly in the post rather than leaving the reader to discover
the script.

## Gap 3 — #193 asks to ESCAPE the segmentation catch-22. We live inside it.

**They wrote:** "require the segmentation is already created, creating a bit of a
catch-22 in that we need labels from hard-to-segment regions that likely do not
contain segmentations."

**We wrote:** labels on "the surface volume's own grid" — which requires a
segmentation — and then reported, as a finding, that "fine-tune gains are
segmentation-bound (+0.094 curated vs +0.011 auto-grown)."

That finding is real and it is *their problem restated*, not their problem solved.
#193 wants label generation that works where no segmentation exists. Ours needs one
first.

---

## What we actually have that they actually want

Do not throw the week away. Reframed honestly, these are real contributions:

1. **The depth-band bug — the strongest card in the deck.** Blindly-centred band
   scores AUC 0.654 vs 0.944 with a measured band. That is a large, specific,
   reproducible defect that *their own pipeline may have*. It is useful to them
   whether or not they take anything else. **Lead with this.**
2. **The condition control** — AUC separating ink from blank sheet *within the same
   text block*. This is the direct test for #192's stated fear ("training the model
   to focus on the underlying surface rather than the ink"). We built the exact
   instrument for the exact worry. Sell it as a validation method, not as labels.
3. **The ruler correction** — component-based letter measures are wrong 3–5× low;
   band-FWHM validated at 2.94 mm against a known 3.00 mm. Anyone measuring hands
   off binarized maps is getting bad numbers.
4. **Spatial-null methodology + two self-withdrawn findings.** Published negatives
   and retractions. Rare, and credible.
5. **The viewer** — browser, no login, streams OME-Zarr from the public bucket.
6. **Four scrolls of calibrated negatives** with stated sensitivity.

## The v4 shape

Stop claiming to deliver #192/#193. Claim what is true:

> **A calibrated instrument, a validation methodology, and a depth-band defect that
> may be in your pipeline — plus partial progress toward #192.**

Then, explicitly and near the top: what is delivered, what is NOT (true voxel-depth
attribution; segmentation-free generation), and what it would take to close each.
State the segmentation-bound result as a *finding about their roadmap* — flattening
quality is the wall, not model knowledge — because that is genuinely useful to them
in planning.

**Honesty is the asset here.** A submission that overclaims against issue text the
judges wrote themselves will be checked in about ninety seconds. A submission that
says "here is a bug you may have, here is a validated instrument, here is what I did
not solve" is the one that gets remembered — and it starts the August 31 clock,
which the handoff already identifies as the real swing.

---

## Do this in a FRESH session

Do not rewrite v4 at the tail of a long context window. The gap analysis is done and
it is on disk — that was the hard part. `/clear`, open `~/Desktop/InK`, read
`HANDOFF.md` and this file, and write v4 with a full tank.
