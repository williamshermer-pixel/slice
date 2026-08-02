# HANDOFF — read this first

*Updated 2026-08-02. The 2026-08-01 block below is still true; this section
sits on top of it and wins where they conflict.*

---

# 2026-08-02 — THE NIGHT THE STRATEGY CHANGED

**No ink was found. The reason we now understand, and it is not bad luck.**

## THE ONE PARAGRAPH THAT MATTERS

Every search this project has run — cross-energy, differential, the calibrated
hunt, the silence audit — operated on FROZEN PUBLISHED PROBABILITY MAPS. The
literature says that does not work: `arXiv 2604.09697` (Apr 2026) shows
test-time augmentation, the standard "squeeze more from a finished model"
trick, *frequently hurts* in weak-signal medical imaging, and a search found no
paper in ANY domain recovering genuinely new weak signal from a frozen map.
ScrollPrize themselves do not do it; their answer to "squeeze more" is
retraining with pseudo-labels. **Our zero survivors were the expected result of
the method, not a fact about the papyrus.**

## WHAT ACTUALLY MAKES LETTERS APPEAR

PHerc. 1667 sat for **two years at 8 µm with zero evidence of letters**. They
rescanned at **2.4 µm / 78 keV / 0.22 m**, re-unwrapped the same regions, ran
the **GENERALIST fragment-trained model**, and letters "jumped off the screen"
— with *"no iterative, scroll-specific labeling"*
(scrollprize.substack.com/p/finallyletters-in-scroll-4, Dec 2025).

We did the opposite: fine-tuned a scroll-specific model **from
`PHerc.1667-iteration-5`**, which their own ablation shows is where the
pseudo-label loop SATURATES. We started at the flat end of the curve.

**We have never run the generalist model.** `scrollprize/PHerc.1667-iteration-0`
is the cross-segment baseline (trained on 500p2a + 658 + two auto-grown
segments, NO labels from the target sheet). 319 MB, full inference contract on
the model card. That is the experiment we still owe.

## THE NEW TOOL — `tools/why_silent.py`

Their July 2026 open-problems doc lists six reasons ink may not appear and then
says *"we do not always know which part of the pipeline is limiting us"* and
*"better diagnostics matter just as much as better models."* Nobody has
published such a diagnostic. This is one. Per sheet, four gates:

| gate | question | basis |
| --- | --- | --- |
| PHYSICS | can the scan resolve ink? | collapse beyond ~3.4 µm (Angelotti, *Sci Rep*, Mar 2026) |
| PROTOCOL | scanned on the recipe? | our measurement, below |
| DATA | does the surface volume exist? | our measurement, below |
| DETECTION | did the model commit? | absolute p99, not a relative cutoff |

No GPU, no model, no labels — HEAD requests and the published maps.

### Scroll 1, all 117 sheets

    INK FOUND     105
    DATA            8      silent because the volume was never written
    UNRECOVERED     4      good scan, real data, model still silent

**Two thirds of Scroll 1's apparent silences are a DATA artefact**, not ink.
The four real candidates, by name:

    20260602204401  2.4um  cov 78.3%  p99 139
    20260603145540  2.4um  cov 82.5%  p99 182
    20260603185441  2.4um  cov 75.0%  p99 175
    20260603190005  2.4um  cov 80.0%  p99 175

Caveat kept honest: `20260701183151` (110 Mpx) landed at 69.4% against a 70%
cut I chose. That is a judgement call sitting on an arbitrary line — re-examine
it, do not let the threshold decide.

## TWO MEASUREMENTS WORTH SUBMITTING

**1. Scan protocol predicts recovered ink.** Across all 420 published maps:

| recipe | n | median p99 | median confident calls |
| --- | --- | --- | --- |
| 2.4 µm / 0.22 m / 78 keV | 80 | 240 | **8.75%** |
| 2.399 / 0.22 / 78 | 76 | 239 | **7.32%** |
| 1.129 / 0.22 / **59** | 74 | 231 | **5.63%** |
| 2.215 / **0.4** / **111** | 47 | 234 | **4.15%** |
| 7.91 (Scroll 5) | 106 | 229 | 4.38% |

Lead with the WITHIN-SCROLL comparison — PHerc0139/0814/1667 appear in both the
78 keV and 59 keV rows, same segments: **7.32% vs 5.63%, ~30% more ink from
78 keV.** The cross-scroll rows are confounded by preservation.

**2. The `-L1` surface volumes are largely unwritten.** Measured by HEAD:
every Scroll 1 `-L1` checked is **29–37% populated** while its 2.4 µm sibling
is 71–85%. Any silence measured on an `-L1` volume is confounded.

**3. Scroll 5 model-vs-model.** 53 sheets, two checkpoints on ONE volume, they
agree on only **38.4%** of each other's calls (×8.6 over a rolled null, 53/53
significant). Two models on identical input disagree MORE than two different
energies do on PHerc0139 (58.9%). `out/disagree_0172/`.

## BUGS FOUND IN OUR OWN CODE — BOTH SILENT

**THE tifxyz SENTINEL IS `-1`, NOT `0`.** `(xyz != 0).any(-1)` calls
`[-1,-1,-1]` VALID. Measured: meshes reporting "100% valid" were 64–70% real;
90–120k phantom points per segment all stacked at one fake coordinate. The tell
was `p10 = 0.00` in the winding-gap table — phantoms matching phantoms at
distance zero. **This corrupted the PHerc0343P adjacency numbers and the
sandwich test.** Correct test: `~(((xyz==-1).all(-1))|((xyz==0).all(-1)))`.
Fixed in `render_native.py`; **`find_seams.py` and `sandwich_0343p.py` still
carry it.**

**NORMALS CANNOT BE TAKEN AT A PATCH RIM.** Central differences straddle the
zero-fill, du and dv come out parallel, the cross product collapses. Measured:
**0 of 694 rim cells** had a usable normal vs 20,781 of 22,950 interior. Filter
on that and you silently empty every boundary — which returned "0 seams" and
looked like a result. Compute on the interior, diffuse outward.

## OPERATIONAL FACTS THAT COST TIME

- **RunPod's REST v1 never returns `runtime`** — not on `GET /pods/{id}`, and
  it reads `None` on the list endpoint even for a live pod. The banked lesson
  "check `runtime`, not `desiredStatus`" **cannot be executed against this
  API.** Do not conclude "no zombies" from it.
- **RunPod's HTTP proxy 404s on this account.** A pod whose entire command is
  `echo HELLO > log.txt && python -m http.server 8000` returns 404 for minutes
  while RunPod confirms it placed on an RTX 4090. Bisect before blaming your
  own script — three pods died to my theories before the minimal probe.
- **Start the log server FIRST in any pod command**, before pip and before the
  job, or you are blind until the job already finished.
- **Local CPU inference works**: `~/.ink-venv` (Intel Mac → torch 2.2.2 is the
  ceiling, so `transformers==4.44.2`, and pin `numpy<2`).

## THE PLAN

1. **Run the generalist** (`iteration-0`) on the 4 UNRECOVERED sheets. Render
   from level 0, **downsample to 2.4 µm** — do NOT feed 1.129 µm to a model
   trained at 2.4; receptive fields are in pixels, so the physical footprint
   halves. Research is explicit that this is unsupported.
2. **Fix the sentinel bug** in `find_seams.py` / `sandwich_0343p.py`, then
   re-run — both prior results are void.
3. **Submit the diagnostic** + the protocol correlation + the `-L1` coverage
   finding. That is a defensible August entry that needs no new ink.

## STRATEGIC READ

The awards go to GEOMETRY AND LABELS, not viewers — $10k (May 2026) to
ScrollFiesta, an *external standalone* mesh-topology repair tool; $200k Kaggle
to nnU-Net for surface detection. A browser viewer cannot mesh, flatten, or
produce tifxyz. But **the extension point is the `tifxyz` format** — ScrollFiesta
never touched their C++.

And: **there is no independent methodological audit of Vesuvius ink detection
anywhere in the literature**, on a pipeline built from human-reviewed
pseudo-labelling loops. We have the nulls, the controls, and now the gates.
That is the lane nobody is competing for.

`tools/render_native.py` renders our own surface volumes from level 0 + mesh
(first in this project) — `--scale 20` = 1.129 µm, `--scale 10` = 2.258 µm
parity. Physical extent comes from the MESH CROP, not from scale.

---

# ✅ JULY 2026 IS SUBMITTED

Form sent, **PR open: https://github.com/ScrollPrize/villa/pull/1295** (three
ScrollPrize code owners auto-requested as reviewers). Repo public, MIT.
Nothing is owed on July.

The submitted answer is preserved in `findings/SUBMIT_NOW.md`.

---

## ✅ THE POSITIVE CONTROL PASSED — 2026-08-01 ~04:40

**Scroll 1's published ink overlay lands on letterform-shaped marks arranged on
baselines.** Seg `20231005123336`, level 5, layer 54 (inside the measured ink
band 27-89). Found by William, by looking, minutes after the overlay went live.

**Stated precisely, because the first version of this note overclaimed.** It
said "readable Greek, three lines of it". What is actually established:

- the white shapes are **ScrollPrize's own published ink detection**, not ours
  and not synthesised. The pipeline is download their ink-map JPEG → threshold
  at the top decile → recolour → composite. Nothing in this repo draws text;
  there is no `fillText` anywhere (checked).
- those shapes are letterform-like and sit on baselines
- **nobody here read them.** No transcription was attempted, no papyrologist
  looked, and "readable" was a visual impression reported as a finding. That is
  the same error this project spent the night correcting.

What it proves is the thing a positive control needs to prove: **the overlay
lands where their detection says ink is.** Not that we read a scroll.

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

## VIEWER CONTROLS — RESOLVED, WITH ONE CAVEAT

Reported as "fit and out don't work". **They were working the whole time.** A
surface chunk carries the entire depth stack of a tile, so zooming out is a
multi-second read and the OLD IMAGE STAYS ON SCREEN until it lands. Click,
nothing visible, conclude dead button.

Verified 2026-08-01 05:20 on the deployed site: Out took the field from 7.2 mm
to 14.4 mm (level 3 → 4). Fit sets the full sheet, which is ~900 chunks and
around 25 seconds on a big segment — slow, not broken.

Fixed: a **reading badge** on the plate showing chunk and MB count while a read
is in flight, so a slow read looks like a slow read.

A mistake worth not repeating: on first report I "fixed" this by clamping Fit
and zoom-out to a read budget, which turned a slow button into one that could
not zoom out at all. Reverted. **Expensive is not the same as broken.**

Also fixed in the same pass: resolution now follows the zoom (the level was
chosen once at open and held, so zooming just magnified a 32× downsample); the
labels panel explains itself instead of vanishing on unlabelled sheets; raw
scroll volumes removed from the viewer.

## RUN THIS FIRST, BEFORE ANYTHING ELSE

```bash
python3 tools/positive_control_xe.py && python3 tools/test_crossenergy.py
```

Both must be green before you trust or change anything. As of the last commit
the gate reports **13 passed, 1 failed** — check 12, "positive control passed
and is newer than every tool". That is not a broken pipeline; it is the gate
correctly noticing that `build_qc_assets.py` and `build_surface_catalog.py`
were edited after the last control run. Rerunning the control clears it. It
takes a few minutes.

Leaving it red on purpose rather than committing a stale green: a green gate
that had stopped meaning anything is the exact failure this whole night was
about.

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
  Scroll 1 overlay lands on letterform-shaped marks on baselines, which is a
  pixel-level confirmation of placement (not a reading — see the note above). The 18 µm/px label grid against a 2.258 µm volume still makes
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
- **A slow read is not a broken button.** Always show that a read is in
  flight. Clamping the view to a budget to make it "responsive" removes the
  feature instead of fixing the feedback.
- **Do not test a deploy by grepping the bundle for comments** — production
  builds strip them, so absence proves nothing. Probe a user-visible string
  literal, or check the chunk hash changed.
- **Wait for the 300 ms URL debounce before concluding a control did nothing.**
  Two "broken" buttons were mis-diagnosed by screenshotting too fast.
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
