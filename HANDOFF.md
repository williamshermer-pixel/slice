# HANDOFF — read this first

*Rewritten 2026-08-01 ~04:15, at the end of the night the July submission went
in. Everything above the "PRIOR HISTORY" line is current. Where they conflict,
this block wins.*

---

# ✅ JULY 2026 IS SUBMITTED

Form sent, **PR open: https://github.com/ScrollPrize/villa/pull/1295** (three
ScrollPrize code owners auto-requested as reviewers). Repo public, MIT.
Nothing is owed on July.

The submitted answer is preserved in `findings/SUBMIT_NOW.md`.

---

## ✅ THE POSITIVE CONTROL PASSED — 2026-08-01 ~04:40

**Scroll 1's published ink overlay renders READABLE GREEK on the papyrus.**
Three lines of letterforms on baselines, seg `20231005123336`, level 5, layer 54
(inside the measured ink band 27-89). Found by William, by looking, minutes
after the overlay went live.

This settles what the previous version of this file listed as the open
question. It means:

- the label→surface coordinate mapping is correct **at pixel level**, not only
  arithmetically (the ±2% figure was necessary, not sufficient — this is the
  sufficient part)
- the overlay pipeline is verified end to end on a sheet whose text was
  independently read and published in 2023
- **PHerc0139 showing formless blobs is confirmed as the HAND SIZE, not a bug.**
  1.61 mm against a 578 µm model field of view returns letter-sized mass;
  3.00 mm resolves letterforms. Our own maps and the published ones agree on
  this. Stop treating 0139 blobs as evidence of a broken tool.

Consequence for where to work: **Scroll 1 is the sheet to develop against.**
Anything that claims to find or show ink should be demonstrated there first,
because it is the only place where success is visually unambiguous.

## THE ONE THING TO DO NEXT

`findings/EDGES_AND_SEAMS.md` — William's observation that segments abut
and words are cut in half at their edges, which our own search deliberately
excluded. Data verified present and cheap (1.5 MB per segment). Best open lead
in the project.

---

## WHAT THE SITE IS NOW

`slice-site-alpha.vercel.app` — deploy by rsync to `~/slice-site` (exclude
`tools/ findings/ out/ samples/ *.md`) then `vercel deploy --prod --yes`.

| route | what it is |
| --- | --- |
| `/` | landing page. Was the CT viewer, which meant the submission link opened on a grey blob |
| `/qc` | **the tool.** 37 PHerc0139 segments, where the two scans agree/disagree/are silent. Click anywhere or use the ranked work queue to open that spot on the papyrus |
| `/record` | the findings, both negative searches, and the failure catalog |
| `/viewer` | CT viewer. Defaults to a labelled sheet. Labels overlay on PHerc0139 (cross-scan) and Scroll 1 (published ink) |

Raw scroll volumes were **removed from the viewer**. A raw scroll cannot show a
letter — the geometry cuts every sheet edge-on — so they were 14 grey blobs
implying you could go looking for text in them.

---

## THE CORRECTED NUMBERS (PHerc0139, all 37 paired segments)

| | |
| --- | --- |
| agreement | median Pearson r **0.455**, Jaccard **0.417** vs null **0.030**, enrichment **14.2×**, all at the 24-roll p floor of 0.04 |
| disagreement | the two published maps agree on **58.9%** of each other's calls |
| search | **no survivors**; 35/37 segments with a usable paired null, smallest p 0.090 |
| coverage | 67.1 cm² searched, **28.7 cm²** can host a letter, 10.2 cm² a four-letter run |
| sensitivity | one synthetic letter at the median amplitude of real calls scores **2.72** against null p95 **2.45** — marginal |
| self-audit | **5 of 28 pairs flagged**, each attributed to the map that disagrees |

**PHerc1667 and PHerc0814 are WITHDRAWN.** They were measured with the
defective instrument, deleted rather than corrected, and there was no time to
rerun before the deadline. Rerunning them is August work and is *lower*
priority than the two items above.

---

## THE LAW THIS NIGHT BOUGHT

**No detector ships without a positive control.** `tools/positive_control_xe.py`
plants a known shift and known synthetic ink and fails unless both are
recovered. `test_crossenergy.py` check 12 requires it to have passed AND be
newer than every tool.

A 13/13 green test suite sat on top of an instrument that could not have found
ink if ink were there. The checks grepped source text, were true by
construction, or compared an output against itself. Full catalog in
`findings/CROSSENERGY_1667.md` — read it before writing any new detector.

The bugs it hid: an inverted warp sign that *degraded* registration on every
segment; a null that was the identity operation (planting real ink made the
test *less* significant); `NULL_N=16` with a `p ≤ 0.05` flag that was
arithmetically unreachable; a Jaccard null that lost call density and inflated
enrichment ~6×; a certifier that read one of two maps and misdiagnosed both its
findings; and 62 shipped certificates asserting a registration measurement no
tool performs.

**Also: `.claude/agents/scientist.md` exists in this repo** — an adversarial
domain auditor built for exactly these numbers. It was never invoked all night.
Use it.

---

## KNOWN BROKEN / NOT DONE

- **Neuroglancer links.** Built, not shipped. The URL is accepted (layer appears
  by name at the right position) but every panel renders blank grey. The volume
  exists and the coordinates are right; the difference from ScrollPrize's own
  working Neuroglancer links is that those load *scroll* volumes while ours are
  per-segment *surface* volumes (multiscale, anisotropic pyramid). Builder and
  reasoning kept in `app/qc/page.tsx`. **William asked for this three times and
  still does not have it.**
- ~~Overlay alignment unverified at pixel level~~ **RESOLVED 2026-08-01**: the
  Scroll 1 overlay renders readable Greek on the papyrus, which is a pixel-level
  confirmation. The 18 µm/px label grid against a 2.258 µm volume still makes
  the overlay 8× coarser and blocky at high zoom — that is resolution, not
  misregistration.
- **Discord post and issue comments not posted.** Drafted in
  `findings/SUBMISSION_DRAFT.md`. These are the only lever on "actually gets
  used", which is the heaviest judging criterion and the one that decides
  August.

---

## THINGS THAT COST TIME, DON'T REDISCOVER THEM

- **Read the wishlist AND the issue bodies.** Not the titles. `#192` demands
  labels "in true 3d rather than a single image projected across multiple
  layers" — a 2D raster is the thing it forbids, and one was built and demoted.
  Also read `scrollprize.org/docs/37_2026_open_problems.md`; it is the real spec
  and it names "stronger diagnostics" and telling "no ink" from "no ink
  recovered yet" as open problems.
- **You cannot see letters by eye in raw CT.** Not even on Scroll 1. That is why
  ink detection is an ML problem. Looking at a slice and seeing nothing is the
  expected result, not evidence the tool is broken.
- **Ink is at layers 27–89 of ~116**, centre ~58. Reading the stack centre
  instead cost AUC 0.654 vs 0.944 against published calls. Largest single effect
  found in this project.
- **Surface chunks are the whole depth stack of a tile** (`[depth,128,128]`), so
  a full-sheet view is a ~385 MB read. `Fit` and zoom-out must be budget-aware
  or they hang and read as dead buttons.
- **Resolution must follow the zoom.** The level was chosen once at open and
  held, so zooming just magnified a 32× downsample. Fixed; keep it.
- **Smoke-test one segment before any fleet run.** Two bad null designs died in
  under a minute that way instead of after a 20-minute sweep.
- **Merge, never overwrite, when writing result JSON.** Re-running one segment
  wiped the other 36. Twice, in two different tools.
- **Terminate RunPod pods at harvest**; check `runtime`, not `desiredStatus`.

---

## PRIOR HISTORY

Everything below this line predates 2026-08-01 and is kept because the
reasoning is load-bearing. Where it conflicts with the above, the above wins.
See `findings/CALIBRATED_HUNT.md` for the earlier differential campaign — that
instrument is SEPARATE from the cross-scan work, was not touched by the fixes
above, and carries its own positive control (16/17 known letters recovered,
~78% per-letter sensitivity). Its numbers stand.
