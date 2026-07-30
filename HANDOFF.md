# HANDOFF — read this first

## ⚡⚡ LATEST (2026-07-30) — THE CALIBRATED HUNT. Read `findings/CALIBRATED_HUNT.md`.

**No new letters. But the instrument is finally honest, and two prior results
are WITHDRAWN.**

- **The 2026-07-29 differential is withdrawn.** Its "9 of 22 segments carry
  letter-sized our-hot/theirs-cold structure" used a RELATIVE threshold
  (top 4% of our map) with no null. Re-run tonight it produced 3 candidates and
  **23 of 24 spatial-null rolls reproduced them** (p up to 0.92). A relative
  threshold selects 4% of pixels whether ink exists or not.
- **Two silent bugs found:** the p96 mask went EMPTY whenever >4% of a map
  saturated (confident silence on our hottest maps), and published-map
  alignment assumed 8× downsample vs the true 8.0006.
- **The replacement instrument, all measured:** letter-scale box mean at his
  1.09 mm hand — **AUC 0.981**, **77.7% per-letter detection** at 0.1% FPR
  (per-pixel thresholding managed only 9.9%); **CONDITION-CONTROLLED AUC
  0.961** with letters **3.8×** above blank sheet of the SAME condition beside
  them (the ink-vs-preservation separation this project had never achieved);
  spillover-safe null (≥2 letter-widths from any called pixel); power **99% at
  five hidden letters**.
- **Result: 78 windows across all 38 PHerc0139 segments, ONE candidate, ZERO
  survivors.** The candidate sat in the **title segment**
  (`20260422000000-title`, 2 clusters, peak 0.382) and died at the spatial null
  (13/24 rolls matched, p=0.56). The margins of *On Gods* are quiet AT A KNOWN
  SENSITIVITY — a calibrated negative, not a blind one.
  `out/lostbook/`, render `out/lostbook/evidence_hunt.png`.
  **Loose end worth pulling: the title region deserves a dedicated native-res
  pass, not one margin-aimed window** — titles are the highest-value target on
  any scroll and this one has never been searched properly.
- **Bounded by:** the model was fine-tuned on this scroll's own published
  calls, so it is biased toward agreeing with them; and "known letters" are
  published-detector output, not human readings — at 1.09 mm neither map
  resolves letterforms, only letter-sized masses.
- **NEXT, and it is the strong play:** this detector is scroll-agnostic and
  never yet aimed at a scroll it can resolve. **Run it on Scroll 1's 3 mm
  hand** (where our renderer demonstrably draws letterforms) and on 1667/0814
  at their measured hands. Every published map on every scroll was binarized
  identically, so the discarded band is the hunting ground everywhere.
  Tools: `hunt_0139.py` + `letterscale_0139.py` + `condition_control_0139.py`
  (retarget TARGETS/hand constants), fleet via `fleet_lostbook.py`.
- Fleet plumbing lesson: the RunPod proxy WAF **403s python-urllib's user
  agent** (broke upload, pod-side fetch AND harvest — use curl or spoof the
  UA), kills PUT bodies much over 8 MB, and the current pytorch image needs
  `pip install hf_transfer`.

## ⚡ STATE OF THE WORLD (2026-07-29 end — superseded above where they conflict)

**What exists:** a PROVEN ink-detection pipeline (streams any scroll from
the public bucket → production-spec renderer: model
`scrollprize/PHerc.1667-iteration-5`, depth band **z27..z89**,
clip[0,200]/255, tiles 256/stride 64, sigmoid-BEFORE-blend, 4-way TTA,
Hann window, max-stretch + defog finish = **AUC 0.944 & drawn letterforms
on Scroll 1 ground truth**; canonical code `tools/pod_final.py`). Plus:
the regenerator (native-res surface rendering, proven on Scroll 1,
`tools/regen_s1.py` — mesh coords are AS-PUBLISHED, native volume is a
partial scan), per-scroll depth calibration, per-scribe hand measurement
(0139: 1.09 mm letters / 4.57 mm pitch), fleet orchestration (RunPod REST,
key in `~/.comfyui-mcp/.env`, ALWAYS terminate pods), the differential
search (ours-hot ∩ published-cold — published maps are binarized), and
laptop-side sweep/gallery tooling (`~/ink-ml/venv`: torch 2.2.2,
transformers 4.57.6, numpy<2).

**What was found:** no new letters (18 mechanisms + every ML candidate
died honestly); the depth-band bug (0.654→0.944); 0139's hand is BELOW
the model's resolution (envelope-only there); 9-segment differential
structure on 0139 that failed shape inspection; native 1.129 µm data is
public for 17 segments; PHerc0172 no-lead bound; the whole story is in
the dated sections below.

**What to do next, in order:** (1) William reads
`findings/SUBMISSION_DRAFT.md` → flip repo public → Discord post,
**deadline July 31 23:59 PT**; (2) fly the **Scroll 1 differential**
(production renderer + defog on its 81 segments, ours-hot vs
published-cold — the best remaining shot at findable letters); (3)
implement the reader per `findings/READER_DESIGN.md` (calibration
harness FIRST); (4) harvest the honest-bootstrap A/B if pod
ju1gcx1wkrg6gq finished (then TERMINATE IT — check `GET /v1/pods`).

**LATE ADD — honest bootstrap A/B: 0.850 → 0.944 (+0.094) on held-out
0139 text with the FIXED renderer.** The tuned model now reads the lost
book's known text at Scroll-1-letters level. Weights:
`out/bootstrap/tuned_0139_honest.pt` (+ holdout maps beside it). This
upgrades the reader's odds on 0139 substantially — the differential and
envelope-mode work should use THIS model's maps.

**Repo state:** everything committed & pushed to the PRIVATE GitHub
(`williamshermer-pixel/slice`, commit b455d4e): all tools/, findings/
(incl. SUBMISSION_DRAFT v2, READER_DESIGN, key renders in
findings/renders/). out/, *.npy, *.pt, mesh tifs are gitignored (big
binaries live on disk only — the tuned weights are NOT in git). Going
PUBLIC is the submission step, William's two clicks.

**House rules:** render before believing; every finding goes to William's
eyes; per-scribe calibration always; no generative models on evidence;
publish negatives; terminate pods.

Session of 2026-07-26/27, updated 2026-07-28 evening. Everything below is
measured unless flagged otherwise.

## UPDATE 2026-07-28 — why every run kept dying, and the fix

Every dead run died the same way, and it was never the science. The dogs were
child processes of whatever terminal or Claude session launched them, so when
that session ended the pack died with it (the 23:05 run died at 00:21 with
Rufus carrying +0.180 penalised on `weave_fill+weave_lift`, four hours before
the machine shut down). Reboots at 14:44 and 15:18 today killed the rest.
`caffeinate` was a printed suggestion nobody ran, and the specks BONE sat
unverified for two hours because verification was a human instruction.

`dogs.py` now has a **herd supervisor**: `--pack` spawns one detached process
(own session, parent = init) that owns the dogs, runs `caffeinate -i` as its
own child, respawns any dog that dies with time on the clock, and **runs
`verify.py` automatically the moment BONE.md appears** (result in
`out/dogs/verify-<ts>.log`, plus a macOS notification). After a reboot:
`python3 tools/dogs.py --resume` — one command, picks up the remaining time
from `out/dogs/deadline.json`.

**2026-07-28 ~20:00: William retired the dogs.** The 14-dog run above was
launched at 19:43 and killed on his call minutes later — seventeen dead
mechanisms and the ~34%-of-sheet-contrast sensitivity floor say the
hand-crafted-feature lane is exhausted, and he asked for the best
letter-finding play instead. The herd infrastructure stays (it is how any
future long run should launch). The falsified specks alert and the aborted
3-minute run are archived in `out/dogs/round-20260728-1516-aborted/`.

The tile cache moved to `~/.ink-cache` (a reboot purged the old
`/private/tmp` cache; see the comment in `tools/pack.py`). The table below is
corrected.

**Then the science deep dive happened — read
`findings/science-deep-dive.md` before doing ANY further detection work.**
Headlines: the field read PHerc. 1667 end-to-end (June 2026) and PHerc. 172's
title (May 2025); our 2.258 µm working resolution is documented by the field
as partially destroying legibility (native 1.129 µm data may exist — check);
and the ink-probability→Greek-prior reader lane is verified open — proposed
by Handmer in 2023, built by nobody, with the hallucination-posture
constraints spelled out in Part II-E.

**Native re-run verdict (2026-07-28 late, `tools/native.py` v3,
`findings/native_rerun2.json`):** paired 17 segments (native 1.129 vs L1
2.258, identical ink-aimed mixed windows, identical params/nulls).
**Resolution was NOT the wall** — deltas ~0 for 9 of 10 features; the
seventeen negatives stand at native res. TWO new things: (1) ink-AIMED
mixed windows lift nearly every feature to +0.10–0.13 excess across 16
segments / 3 scrolls at BOTH resolutions — the old dead-centre crops were
diluting every measurement (crop placement is a method finding); (2)
`sharp` is the exception with a real resolution delta: +0.077→+0.159
(+0.082, 17/32 windows significant, positive on both multi-segment scrolls:
0814 +0.130, 1667 +0.204). Within-window ranking = the reader's likelihood
question, so this feeds the reader directly. Robustness pass at fresh
windows (INK_AIM=0.30, tag 4) launched; caveats: labels are CNN output, no
blank-window control yet, PHerc0139 has only 1 native segment.

**THE AIMED-WINDOW FINDING — KILLED 2026-07-29, negative eighteen, and the
best autopsy of the project.** The block below records it as it looked at
its peak; the kill chain follows it. Read both — the artifact mechanism is
the publishable part.

**The kill chain (all measured, `out/evidence_cityscape.png` /
`evidence_weave_amp.png`):** (1) The evidence render — William's cityscape
idea — showed the scored maps were smooth corner-to-corner RAMPS, not
letterforms, and windows aimed at 30–40% coverage sit at text-column edges,
so "ink on one side" is systematic geometry. High-passing at letter scale
collapsed weave_fill +0.205→+0.084, hfenergy +0.234→+0.093, sharp
+0.134→+0.042. (2) The apparent survivor (weave_amp hp +0.222) was riding
the box-filter EDGE FRAME (a 155 px artifact band, ~30% of the window);
neutralising the band: **weave_amp +0.081, weave_fill +0.050, hfenergy
+0.071 — all below the 0.09 bar.** (3) Why the blind control stayed silent
anyway: PHerc0172's diffuse labels don't create the same edge geometry —
the control was silent for the wrong reason. LESSON: a candidate can clear
spatial nulls, independent replication, AND a physics control while being
pure window-geometry artifact; only the evidence render caught it. Render
before believing. The feature era is now closed WITH FINALITY — eighteen
mechanisms, every death understood.

**Original block, preserved (2026-07-28 late):** Within ink-aimed mixed windows (~0.6–2 mm, 30–40% label
coverage), the texture/weave family ranks ink pixels far above the spatial
null: `weave_fill`/`weave_amp` **+0.20 to +0.22 AUC excess, 75–79% of
windows individually significant**, `hfenergy` +0.18–0.21, on 14–16
segments across 3 scrolls, at BOTH 1.129 and 2.258 um. Replicated on two
independent window draws (cov targets 0.40 and 0.30 — different windows,
same result). **Blind-scroll control passed** (`tools/window_control.py`,
`findings/window_control.json`): identical aiming and scoring on 14
PHerc0172 windows, where the ink was never sampled, gives weave_fill
**−0.010** (1/28 sig), weave_amp −0.021, hfenergy −0.024 — zero where ink
cannot be, +0.2 where it is. `offaxis` keeps a small blind residual (+0.039)
consistent with its known confound personality; treat it separately.

What it is: a reproducible, controlled, WINDOW-LEVEL ink-ranking signal in
hand-crafted features — the thing whole-tile scoring buried all week
(crop placement was diluting every measurement). What it is NOT: a reading.
No parameter search occurred (2 fixed draws) so selection effects had no
room to operate. Remaining caveats: labels are CNN output (we match a
working detector, which caps meaning), and PHerc0139 contributes only 1
native segment. NEXT: evidence renders (feature map beside ink map, human
eyes on it), then this becomes (a) the reader's image-likelihood term and
(b) the submission's headline positive alongside the negatives.

**THE MAP FACTORY IS LIVE (2026-07-29, CPU + GPU).** The official
`scrollprize/PHerc.1667-iteration-0` ink model now runs end-to-end on both
the laptop and RunPod. Everything needed to reproduce:

- **Convention (measured, `out/sweep_conv.log`): layers 0..62 of the surface
  volume, NO flip, clip[0,200]/255 float32** ("intensity in roughly [0,1]" —
  the model card line the first attempt missed; 0-200 input saturates the
  net into border garbage). Tile 256, stride 128, sigmoid at quarter-res,
  average-blend. Laptop validation vs published map: **AUC 0.813** (1024px
  window); GPU 9.2mm window: AUC 0.685, r +0.31 (regional variance + a
  2024-era comparison map).
- **Version pins that work: torch 2.2.2 + transformers 4.57.6 (laptop,
  `~/ink-ml/venv`); pod = runpod/pytorch:2.4.0-py3.11 image +
  `transformers==4.57.6`.** Unpinned transformers breaks two ways (DTensor
  import vs torch<2.5; 4.46.x chokes on this model's safetensors metadata).
- **Pod recipe (`tools/pod_job.py`)**: self-contained job baked into
  dockerStartCmd as base64; streams S3 at datacenter speed (**1024 chunks /
  1.9 GB in 8 s**), serves results via http.server on port 8000
  (`https://<podid>-8000.proxy.runpod.net`); 961 tiles inferred in ~1 min.
  RunPod REST API + key in `~/.comfyui-mcp/.env` (key `ink-4090` created
  2026-07-29); 4090 SECURE $0.69/hr (COMMUNITY had no capacity); **pods were
  terminated after each run — verify none is billing** (`GET /v1/pods`).
  Total spend for the whole saga: well under $1.
- **Map factory v1 quality**: reproduces the text GEOGRAPHY but output is
  tile-blocky — not yet letterform-grade. Next knobs: stride 64 (8×
  oversample), average logits pre-sigmoid, and larger context. The reader
  needs ranking quality in marginal zones, not cosmetics.
- **v2 (stride 64 + logit-averaging, `out/gpu/wide_sharp*.png/npy`): blocks
  4× finer, first shape-level agreement with the published map (matching
  letter-mass inside the same 3 mm box), AUC unchanged 0.686 — oversampling
  is cosmetic to ranking, as expected. William can now read these maps
  himself (spotted letterforms unprompted). All pods terminated after use.
- **William's reference card**: `out/letters_reference.png` — real found
  letters from Scroll 1 + 1667 with scale bars; his read-the-map training.
  His standing rule: every finding ships as a render to his eyes.

**READER v0.1 RAN (2026-07-29 late) + WILLIAM'S TWO DESIGN CALLS.**
`out/first_decode.png`: four letter-gate candidates in his chosen region
scored against blurred ideal capitals — all honestly too-close-to-call
(best: Μ 0.59 vs Θ 0.58). His letter-test on the same region:
`out/william_crop_lettertest.png` (sizes 2.9/2.5mm vs 3.0mm hand; 1.86mm
advance rhythm +0.34). Charts made: `out/hunters_alphabet.png` (capitals
ranked by blur-trust; sigma=C, omega=ω, no lowercase existed) and
`out/scribes_hand.png` (60 unlabeled harvested letterforms).

William's calls, now plan of record for the reader build:
1. **Label the handwriting from the deciphered scrolls**: align published
   transcriptions (PHerc1667 paper / DCLP) to map coordinates → thousands of
   LABELED real letterforms from the actual scribe → replace the font
   stand-in templates. Alignment (column/line → pixels) is the build step.
2. **His Ν-vs-Μ dissent stands logged**: pixel-correlation scoring reads
   blob mass, not stroke topology (Ν never made top-3 where a human sees
   Ν). Score stroke structure, not overlap. Human gate overrules nothing
   silently; disagreements are data.
   **THE BET (2026-07-29, end of night): William formally calls Ν on the
   letter-mass in his crop** (the GPU window's top-left quadrant, the
   region of `out/william_crop_lettertest.png` / `out/first_decode.png`;
   machine's tied call was Μ/Θ). When transcription alignment lands,
   look up this exact position in the PHerc1667 published text and grade
   BOTH. First scored human-vs-machine disagreement of the project.
Also queued: harvest templates from fragment PHOTOS (real ink photographs,
in our bucket) + GP banner region + full-res (non-ds8) ink maps — the
"blobby handwriting" fix. First reader exam: decode his region blind, then
grade against the scholars' transcription.

**WILLIAM'S TRAINING DOCTRINE (2026-07-29, confirmed): the reader trains on
the REAL specimens — the GP recovered columns (scrollprize.org
img/grandprize/col-*.webp, local copies in out/), the fragment IR
photographs (actual pen strokes, in-bucket photos/ + Kaggle release), and
transcription-labeled letterforms — NOT on font stand-ins and NOT on ds8
thumbnails.** Specimens already downloaded: `out/scroll1_column.png`,
`out/fragment_ir_photo.png`.
**Doctrine amendment (his call, same night): do NOT assume one hand. The
library had multiple scribes; template banks are PER SCROLL (per hand where
scholars distinguish them), and cross-scroll transfer is TESTED, never
assumed — consistent with the measured 7× condition spread.**

**Registration status (post-scout, 2026-07-29 ~00:30):** villa source
(authoritative, fetched to scratchpad/villa-research/): tifxyz values ARE
level-0 voxel coords of the associated volume, NO offset/scale on XYZ
(meta "scale" is only the 20-voxel grid step); mapping x.tif→zarr axis2,
y.tif→axis1, z.tif→axis0, Z<=0 invalid; `vc_render_tifxyz` applies an
EXTERNAL affine JSON (transform_schema: p_fixed = M @ p_moving, 3x4, XYZ
order) when mesh frame ≠ volume frame; normals usually need --flip-normals.
**No transform JSON exists anywhere in the bucket** (transforms/ and
registration/ prefixes empty; mesh/intermediate/ holds only OBJs +
tifxyz_original/ + tifxyz_normalized/). Overshoot is NON-UNIFORM
(x 1.003× / y 1.13× / z 1.62× of dims) → un-applied rotation+translation,
not a scale. NEXT SESSION FIRST JOB: empirical affine fit — fetch one
~1024³ block into RAM, optimize the transform so mesh samples show
sheet-profile peakedness (bright at 0-offset, falling both sides along the
normal), coarse-to-fine; then regenerate a known-letter patch at native res.

**FIT ATTEMPTS 1-2 (2026-07-29 ~01:00, `tools/pod_fit.py`, both on pods,
both terminated, ~$1 total): two scoring functions measured DEAD.**
(1) Brightness+peakedness at level 5 (36 µm): landscape FLAT — every
config ~87; windings blur into uniform soup; also v1 wrongly REQUIRED full
containment (the volume is a crop — partial overlap is expected).
(2) Gradient-alignment (normals vs local gradients, partial containment
allowed): winner scored align 0.71 BUT bright ≈ 1/255 — the fit parked the
mesh in EMPTY space; sparse mask-boundary gradients gamed the score; proof
render pure black (`out/fit_proof.png`). Runner-ups with different perms
scored 0.6+ — the objective is not discriminative.

**V3 RAN (2026-07-29 ~02:00, `tools/pod_fit3.py`, transform in
`out/transform_v3.json` — NOT TRUSTED): the correlation anchor worked
mechanically (6000 anchored points, surface spread 37, chunk path needs
level/depth/row/col — `/0/0/{cy}/{cx}`) but the result is a PLATEAU, not a
lock: top corr +0.137 refined 0.165 with five DIFFERENT perms/scales at
0.128-0.132. A true lock towers at 0.4+ alone; a weak crowd across
contradictory geometries = every pure flip-and-slide merely grazes truth =
**the transform contains genuine ROTATION. Road one (signed-perm search) is
exhausted — three scoring generations, each eliminating an assumption
class (~$3 total).**

**SOLVED 2026-07-29 ~02:40 — THE REGENERATOR WORKS. THE MESH WAS RIGHT ALL
ALONG.** `tools/regen_s1.py`, proof `out/regen_s1_proof.png`: coordinates
AS-PUBLISHED (scale 1, x.tif→axis2 / y.tif→axis1 / z.tif→axis0, no
transform, no rotation) render FACE-ON PAPYRUS at native 1.129 µm. The
"impossible" z-range was because **the native volume is a PARTIAL scan of
the scroll (~68 mm of ~110 mm; the 2.4 µm volume is 182 mm long)** — the
segment simply extends past the scan's end; in-volume fraction at s=1 is
52.0%, and layer means fall 90→62 across the sheet (the surface-crossing
signature). Every fitter failure was chasing v0's own /2-scale ghost. All
fit tooling (pod_fit*.py) retained as negative-methodology material.
MONEY SHOT v1 DONE (`tools/regen_letter.py`, `out/money_shot.png`):
known-letter window, ink map | published 2.258 render | ours —
**feature-for-feature IDENTICAL structure = registration PERFECT.** But no
visible resolution gain yet because v1 sampled at UP=8 → ~2.8 µm steps,
COARSER than the published render. **v2 fix: UP=20 (one sample per native
voxel, M=1920²) — that render is the true 1.129-vs-2.258 crispness
comparison and the submission centerpiece.**
v2 RAN (`out/money_shot_v2.png`) — but the triptych composition downsizes
both renders to 768px, so overview scale can never show a resolution
difference. **THE COMPARISON IMAGE MUST BE 1:1 ZOOM CROPS: a ~0.3 mm
region shown at full pixel density from both renders (ours 1920-grid vs
published 960-grid), side by side.** Ten-line composition over data
already rendered; FIRST artifact of next session. If crisper: submission
centerpiece. If identical: honest finding that the published render
already saturates the scan (then the campaign leans on reader + labeled
hands, and the native corpus still doubles training pixels). Also: the native volume's
partial coverage means checking which segments/regions (incl. title zone)
fall inside its 68 mm before promising native renders there; the 2.4 µm
whole-scroll volume + its VERIFIED mesh is the everywhere-fallback. then the model
on regenerated native patches; then the title region IF it falls in a
scanned portion (check all four 2026 volumes' coverage — 2.4 µm covers the
WHOLE scroll and its mesh registration is VERIFIED-FITTING, so 2.4 µm
regeneration works everywhere TODAY).

**ROAD TWO (superseded, kept for reference): register the VOLUMES, not the mesh.** The classic
7.91 µm Scroll 1 masked volume is public; the mesh plausibly lives in that
canonical frame (× resolution ratio — the on-7.91 mesh bbox supports it).
So: rigid/affine volume-to-volume registration (SimpleITK, mutual
information, coarse pyramid levels — standard tooling, pod-friendly)
between old 7.91 volume and new native volume; then
mesh→native = (old→new) ∘ (×7.008 scale). Deterministic, rotation-capable,
uses the exact machinery the field's own find_transform.py wraps.
Alternatively run their find_transform.py directly. THEN regenerate.

Original v3 design note, kept: anchor on the published render.** The segment's own L1 surface volume IS the output of
the correct transform. Mesh grid (row,col) ↔ L1 canvas (row*10, col*10)
(grid step 20 level-0 vox; L1 canvas at 2× downsample). So: fetch the L1
mid-layer values S_i for ~6k mesh gridpoints in a compact region; score a
candidate transform by PEARSON CORRELATION between S_i and the native
volume sampled at T(P_i). Real texture matching — black space correlates
~0, wrong perms decorrelate, single global optimum at truth. Reuse
pod_fit's search harness (perm/sign × s∈{0.5,1} × translation grid,
partial containment) with this score; refine winner incl. small rotations;
then proof-render. Also viable: once coarse-correlated, upgrade to
landmark least-squares for the exact affine.

**THE REGENERATOR (2026-07-29, v0 built — `tools/regen.py`) — the
Title-Prize weapon, one registration step from working.** Goal: resample
Scroll 1's PUBLIC native 1.129 µm raw volume along the PUBLIC per-segment
meshes to regenerate native-res surface volumes nobody has published
(2.258 is all that ships; the field documents 1.1→2.4 µm legibility loss;
the title region shows no ink at current res — this is the "new method"
lane, $50k + monthly-tier material).

State: GP-banner segment's native-registered mesh downloaded
(`out/mesh_{x,y,z}.tif`, grid 5374×3865, 87% valid, meta bbox
x 16962–32444 / y 13422–40652 / z 2818–97287). Native masked volume =
(z,y,x) 59969×36006×32354, scale [1,1,1], chunks 128³ uncompressed.
**THE PUZZLE: mesh coords are in the CANONICAL whole-scroll frame (matches
the 7.91 µm mesh × resolution ratio); the masked volume is a CROP with NO
offset/translation recorded in .zattrs — a real documentation gap (the
project's 4th). Mesh z-SPAN (94469) exceeds volume z-dim (59969), so a
scale factor (~0.5?) is also in play. Tried: coords/2 with both y/x
permutations — both render EDGE-ON WINDINGS (slicing across sheets, the
classic wrong-geometry signature; see `out/regen_proof.png`, gorgeous but
wrong).** v0 sampler works end to end (~500 chunks/3 min, on-demand cache).
NEXT: empirical registration — optimize (scale, dz, dy, dx) to maximize
material-hit/sheet-likeness over sparse mesh samples, coarse-to-fine; or
find the crop bbox in villa tooling/community docs. Then: face-on native
patch of KNOWN letters vs the published 2.258 product = William's training
material + reader templates + the August submission money shot.

**MARGIN SWEEP FINDING (2026-07-29 ~03:30, the night's last measurement):
PHerc0139's PUBLISHED ink maps are effectively BINARIZED** — p50=0,
p90≈32, faint band (85-140) only 0.3-0.5% of pixels. The uncalled
"whisper band" the reader needs DOES NOT EXIST in published JPEGs; they
were cleaned before publication. **Consequence: the margin hunt for
uncalled letters MUST run on maps WE generate (the GPU map factory's raw
sigmoid outputs), not on published maps.** Sweep machinery works
(letter-test gates over sliding windows, top-K gallery for William's
eyes — inline script preserved in session, gates: faint band, called<4%,
2-9 letter-sized comps, 1.86 mm rhythm); it just needs our maps as input.
Pipeline for the lost-book hunt: map factory over 0139 segments (GPU,
minutes each) → margin sweep → William's gallery → reader grades.

**THE FIRST WHISPER CANDIDATES (2026-07-29 ~04:00 — the night's true
finale).** Full pipeline ran end-to-end on the LOST BOOK for the first
time: map factory on PHerc0139 seg 20250108000000-w025 (margin-aimed
window [11136, 22272, 4096]; our map hit **AUC 0.906 / r 0.658 vs
published calls** — best agreement of the project), raw sigmoid map saved
(`out/pred139.npy`, 9.03 µm/px quarter-res; **continuous distribution
confirmed — whisper band p90–p97 covers 7%**, proving raw maps carry what
published JPEGs discard). Margin sweep over the whisper band (gates:
called<3%, faint 2–40%, 2–9 letter-sized comps ≥200 px, 1.86 mm rhythm):
**ONE window cleared — two letter-sized whisper components, rhythm +0.26**
(`out/whisper_gallery.png`, sent to William). NOT letters — candidates,
queued as the reader's first real caseload alongside his Ν bet. Rerun
recipe: pod_job_139.py (aim 0.12) → sweep script (inline, params above).
**CAVEAT (William's catch, ~04:15): the sweep gates used SCROLL 1's hand
(3.0 mm letters, 6.18 mm pitch) on 0139 — violating his own per-scribe
doctrine. BEFORE the next sweep: measure 0139's OWN hand from its called
regions (line pitch by row-autocorrelation, letter height by component
stats on called text; 38 segments available) and retune the gates. The
two candidates must be RE-GRADED under 0139's real hand.**
**RE-GRADED 2026-07-29 ~04:40 — MEASURED AND RETRACTED. 0139's hand
(from 180 called components, 6 segments): letters median 1.09 mm
(p25 0.92 / p75 1.63), line pitch 4.57 mm — A THIRD of Scroll 1's hand.
Re-swept pred139 with tuned gates (0.7–2.2 mm comps, 0.70 mm advance):
ZERO windows clear — the two earlier "candidates" were wrong-ruler
artifacts (2–4 letters tall at this hand = condition patches, not
letters) and are WITHDRAWN. This margin window is CLEAN SILENCE under the
correct calibration — the first properly-calibrated margin search of the
lost book. One window of one segment ≠ the book: 38 segments remain, and
every future sweep now uses per-scroll measured hands (William's rule,
vindicated same night it was made).**

**FLEET DAY (2026-07-29 midday): 13 lost-book segments mapped, 3 artifacts
killed, the instrument's floor found.** `tools/pod_fleet.py` + tuned
`fleet_sweep.py`: 13/16 segments' margin windows mapped raw (27 min, one
4090 run; maps in `out/fleet/`). Under 0139's measured hand, 3 windows
cleared gates — **all three REJECTED at the shape test: grid-locked
squares, no stroke shapes** (`out/fleet_gallery*.png`). Lesson stack:
(1) per-scroll hand calibration is mandatory (his letters are 1/3 of
Scroll 1's); (2) the whisper band exists ONLY in our own raw maps;
(3) at stride 128 the model's 0.29 mm output grid CLUMPS into letter-sized
false candidates on a small-hand scroll — size+rhythm gates saturate at
artifact level, so SHAPE discrimination (reader letterform matching) is
the required next gate; (4) 8× oversample dissolve-test of the 3
candidates RUNNING on pod d3tfqbacwjg3xi (A5000 $0.44/hr, stride 32,
4 segments, ~2 h) — artifacts melt, real structure survives. After that:
the bootstrap fine-tune on 0139's called text is the power upgrade.

**BOOTSTRAP ROUND 1 — IT WORKS (2026-07-29 afternoon, the campaign's
biggest positive).** `tools/pod_train.py` on an A5000 ($0.44/hr, ~40 min):
fine-tuned `PHerc.1667-iteration-0` on 6 segments of PHerc0139's called
text (400 steps, AdamW lr 3e-5, batch 4, mixed-cov 256px crops, BCE on
64x64 labels), validated on held-out segment 20260112000000-w043 it never
saw: **AUC 0.713 (baseline) -> 0.825 (tuned), delta +0.112.**
Specialization to the scribe's hand is PROVEN on this scroll. Artifacts:
`out/bootstrap/` — tuned weights `tuned_0139.pt` (320 MB, torch
state_dict), holdout base/tuned maps, A/B render `out/bootstrap_ab.png`.
ROUND 2: use the tuned model to re-map margins fleet-wide (load state_dict
onto the HF model on-pod), harvest its confident new calls as expanded
training data, repeat. This is the 2023 Scroll-1 playbook running on an
unread book — and it is Thursday-submission material on its own.

**THE ZONE (2026-07-29 evening — strongest candidate of the campaign).**
Segment PHerc0139 w028, margin window canvas [10264-11864, 15728-18248]
(zone = pred px 550-950/220-850 of `out/fine/pred_3.npy`): ONE contiguous
~4 mm region where 5 overlapping sweep windows fired. Survived: 8×
oversample (not grid artifact), tuned-model re-examination (4/5
brightened/held; `out/confrontation.png`), and the physical look —
**`out/zone_overlay.png`: model hot-zones sit on CLEAN WEAVE, avoid dark
damage, and one lands exactly on a fine-crackle patch** — the OPPOSITE of
the condition-artifact profile. Still NOT letters (sub-visual at his 1.1 mm
hand; human eyes cannot resolve his strokes against weave). Renders:
battlefield_w028.png, zone_papyrus.png, zone_overlay.png. NEXT GATES:
native-res regeneration of the zone (0139 raw 1.129 zarr exists),
bootstrap round 3 (add zone-adjacent calls, remap), reader templates.
Fleet infra: pod_fleet.py / pod_train2.py (train+remap combo, reproduced
+0.112 twice to 4 decimals). ALL PODS TERMINATED.

**THE LETTERFORM CONTROL — THE FLAW IS OURS (2026-07-29 late, the single
most important result of the campaign).** `tools/pod_job_scroll1.py` on the
GP segment (Scroll 1, 3 mm hand, dense KNOWN-legible text, stride 32 =
8x oversample, 14641 tiles): **published map shows plainly readable Greek
letters; OUR map of the same papyrus shows only blobs** (AUC 0.654,
r +0.327 — regional agreement, zero letterform structure).
`out/wide_scroll1.png`, `out/pred_scroll1.npy`.

**Therefore: every blobby map this project has produced is OUR map-making
failing, not the scrolls being unreadable.** Ruled out as causes: model
choice (this IS the official model), oversampling (8x here), scale prior
(letters are 3 mm here, 5x the tile FOV of 0.58 mm — and the field's own
models have the same sub-letter FOV yet produce legible maps).

**FIXED SAME NIGHT (`tools/pod_fix.py`, `out/fix_sheet.png`, matrix on
known letters): AUC 0.654 → 0.944.** The recipe that draws letters:
**depth band z27..z89 of the 116-layer stack (NOT centred — we'd been
reading the wrong layers all day), model `PHerc.1667-iteration-5` (NOT
the iteration-0 ablation), Gaussian-weighted logit blending.** Depth
dominates (sheet shows letters appear/vanish with the band), model second,
blending third. `tools/pod_job_fixed.py` = the canonical fixed renderer.
CONSEQUENCE: every prior map is obsolete; re-map 0139 margins + the Zone
with fixed settings (and re-check depth band per scroll — 0139 stacks may
carry a different ink layer position; sweep z per scroll before mapping).
Note: every fine-tune result earlier used the WRONG band + iteration-0 —
the bootstrap gains likely UNDERSTATE what the fixed pipeline can do;
re-run bootstrap after remapping.

**CONFIRMED AT SCALE (`out/letters_final.png` / `pred_letters.npy`): the
fixed renderer DRAWS LETTERS.** Full 9.2 mm Scroll-1 control window,
fixed settings: our map now shows the same letterforms as the published
map — same shapes, same positions, coarser but unmistakable (AUC 0.812
mixed window / 0.944 dense cell; the morning's broken renderer scored
0.654 with zero letterforms). The instrument is proven end to end on
ground truth. First letters ever drawn by this pipeline: 2026-07-29
night. (Known letters — the honest kind first.)

**THE HONEST VERDICT (2026-07-29 night, `tools/pod_hunt.py`,
`out/hunt/`): 0139's ink band calibrated at z27 (0.827 on its called
text, clean unimodal peak — same band as Scroll 1). Four margin windows
remapped with the FIXED renderer: 0 windows clear the his-hand gates.
THE ZONE IS WITHDRAWN — an artifact of the broken renderer's wrong depth
band.** Searched territory now genuinely quiet: 4 margin windows of 4
segments, honestly. 34 segments unsearched. NEXT: bootstrap round 2 on
honest z27 maps (should exceed the broken-lens +0.112), fleet the
remaining margins with the fixed renderer, reader on top. The instrument
is finally trustworthy — every future silence and every future candidate
means what it says.

**THE FULL LOST-BOOK SURVEY (2026-07-29 night, `tools/pod_map.py` ×5
parallel pods, ~$2.30, 40 min): 22 of 38 PHerc0139 segments' margin
windows mapped with the PROVEN renderer (iter-5, z27, gaussian, stride
64); maps in `out/book/`.** 12 segments skipped honestly (shallow stacks
< 89 layers, or no ≥2%-ink window). Sweep under his measured hand:
**4 windows cleared, all judged artifact on shape — merged masses
spanning 2–4 letters, no stroke structure, no baseline rhythm**
(`out/fleet_gallery.png`). Repeat offenders w041/w055 worth one closer
look. **Bottom line: the margins of Philodemus' On Gods are QUIET at this
instrument's sensitivity — the first calibrated survey of an unread book,
and a publishable negative.** What that leaves: (a) the reader
(letterform shape-scoring, the only untried gate), (b) bootstrap rounds on
honest z27 maps (never yet done — all fine-tunes used the broken lens),
(c) the 12 skipped segments via the whole-scroll 2.4 µm volume, (d) the
resolution ceiling itself — his 1.1 mm hand may simply sit under what a
model with 0.29 mm output blocks can resolve, which would be the real,
final finding of this campaign.

**THE DIFFERENTIAL — THE RIGHT SEARCH, FOUND LATE (2026-07-29 night).
STRATEGIC ERROR NAMED: all day I hunted LOW-COVERAGE margin windows —
which are blank papyrus BY DEFINITION. Undiscovered letters are not where
both instruments agree there is nothing; they are where OUR map is
confident and the PUBLISHED map is empty.** Published 0139 maps are
binarized (p50=0, faint band 0.3-0.5%), so everything marginal was
discarded at publication — that discarded band is the hunting ground.
Implemented on the laptop, no GPU: ours > p96 AND theirs < 60, then
his-hand component gates + advance rhythm. **Result: 9 of 22 segments
carry letter-sized our-hot/theirs-cold structure; top: w048 (3 comps,
r+0.23), w059 (5 comps, r+0.12, and the mask sits in a LINE along the
published text band — the signature of unread line-ends), w037, w038.**
`out/differential.png`. NOT confirmed letters — but the first candidate
set shaped like text rather than damage. NEXT: (1) regenerate/native-res
those 9 spots, (2) reader letterform scoring on the differential masks,
(3) run the differential on ALL scrolls (it costs nothing and every
published map on every scroll was binarized the same way — this is the
cheapest new-ink search available and it has never been run by anyone).

**PRODUCTION RENDERER BUILT + THE STRATEGIC PIVOT (2026-07-29 latest).**
Scout read the actual production inference code (villa optimized_inference,
GP winner, title-prize; snippets in scratchpad/villa/): the gaps were
(1) GP max-stretch finish (one line, the "punchy look"), (2) real 4-way
TTA (title-prize style, mean of probs), (3) ALL production repos blend in
PROBABILITY space post-sigmoid (logit-blending was our own invention),
(4) Hann window. Confirmed absent everywhere: auto depth selection,
ensembling. Built as `tools/pod_final.py` (iter-5, z27, prob-blend, TTA-4,
Hann, GP finish). Run on both targets (`out/final_scroll1.png/npy`,
`final_w059.png/npy`): **Scroll 1 = clean letter-cluster geography, seams
gone (TTA smooths slightly); w059 = NO letterforms — bright wash + damage.
The differential's 0139 marks do not sharpen under production-grade eyes.**

**CONCLUSION AFTER THE FULL ARC: 0139's 1.1 mm hand sits below this
model's resolving power (0.29 mm output blocks), with every rendering
improvement now exhausted. THE PIVOT: run the DIFFERENTIAL HUNT on
BIG-HAND scrolls (Scroll 1's 3 mm hand — where our renderer demonstrably
draws letterforms — plus 1667/0814 at their measured hands): ours-hot vs
published-cold, production renderer, letterform-scale gates. Also still
open for 0139: the reader's template shape-scoring (sub-resolution
matching is exactly what matched filters are for — but note tracers'
correlated-noise lesson), and bootstrap on honest maps. Submission
Thursday carries: depth-band bug+fix, per-scroll calibration, the 22-seg
survey, the differential method, production-renderer replication.**

**THE DEFOG (2026-07-29, closes the "why does ours look like shit" arc):
display fog is killed by threshold-sigmoid + unsharp** (see inline recipe
in session: max-stretch → sigmoid(gain 22 around p70) → unsharp r6/1.4;
`out/defog.png` — our Scroll 1 map now reads like a published map).
Three fog sources named: averaging fog (fix: narrower kernels/max-blend),
indecision fog (fix: fine-tune), display fog (fixed, free). Standard
final step for all renders going forward.

**BUILD-IT SESSION CLOSE (2026-07-29 latest): the three missing pieces
addressed.** (1) Honest-lens bootstrap A/B running on pod ju1gcx1wkrg6gq
(iter-5/z27/gaussian train recipe, SEGS_MAP empty — pure A/B; TERMINATE
after harvest). (2) **SUBMISSION_DRAFT.md rewritten v2** — leads with the
depth-band failure mode, then per-scribe calibration, the 22-segment
survey, the differential method, production replication + CPU recipe;
ready for William's read + two clicks before July 31 23:59 PT. (3)
**findings/READER_DESIGN.md written** — full architecture: local-null
percentile scoring (defeats the measured correlated-noise failure),
shape vs envelope modes (respects the 0139 resolution ceiling),
calibration-harness-first with shuffled-alphabet control, hallucination
posture, per-scribe template doctrine; first milestone = calibration
curve on one 1667 column; Opus-implementable as written. REMAINING
NOT-BUILT: viewer Ink Bench + labeling UI (Opus, against PLATE & LEDGER
spec); Scroll 1 differential fleet (recipe-ready, fly anytime).

**The original suspects list (all four confirmed relevant), kept:**
1. **Depth band.** We take 62 layers from the MIDDLE of the stack
   (`z0 = D//2 - 31`) and clip [0,200]/255. The field's recipe is
   `START_LAYER=1..63` — i.e. layers 1-63 measured from the SHEET FACE, not
   the stack centre. If the ink layer sits off-centre we are averaging it
   away. TEST FIRST: sweep the depth-band offset on this exact Scroll 1
   window and watch letterforms appear/disappear.
2. **Aggregation.** We average logits over overlaps then sigmoid; the field
   Gaussian-weights per-tile predictions and takes the max across TTA.
   Flat averaging over 8x overlap is a low-pass filter — plausibly the
   direct cause of blob-ification.
3. **Normalisation.** Per-tile clip[0,200]/255 vs per-volume percentile
   normalisation: a wrong contrast window flattens the crackle signal.
4. **Model variant.** `PHerc.1667-iteration-0` is an ABLATION checkpoint
   (iteration 0 of 6!). `iteration-5` and `scrollprize/ink_canonical_2um`
   (r152, 1.44 GB) are the mature ones. Try iteration-5 next.
Fix any of these and EVERY map (0139 margins, the Zone) gets re-made
sharper — the Zone verdict is deferred until then.

**Measurement 0, both halves done 2026-07-28 night:**
(a) `tools/lead_sweep.py` swept every depth layer of PHerc0172's full stacks
— flat at all depths (hp ≤ +0.064 sd, inside the null envelope). **The
physics control stands**; no lead-driven contrast exists in the public
7.91 µm data, a direct check on the community's stated hypothesis.
(b) Bucket audit: **native 1.129 µm surface volumes are PUBLIC for 17
segments** (8×PHerc0814, 8×PHerc1667, 1×PHerc0139) as non-`-L1` zarrs beside
the ones we read; Scroll 1 has native RAW + published meshes, so its native
surface volumes can be regenerated locally. Next builds: `pack.py` prefers
non-`-L1` zarrs → re-run the physics features at native res; PHerc1447 CPU
inference with the public canonical model; the reader (see deep-dive Part
III).

**STRIKE CORRECTION (2026-07-29 early):** PHerc1447's surface volumes are
**8.64 µm/voxel = 1.7 voxels through the ink — physics-blind by our own
founding number.** `data-capabilities.md`'s "run blind on PHerc1447" call
never cross-referenced the resolution table; fixed here. Surveyed Scroll 1:
80/81 segments with surface volumes ALL have published ink detections —
**there are NO virgin good-resolution segments anywhere in the public
bucket.** Consequence: no cheap new-ink strike exists on S3; the remaining
new-ink lanes are (a) the READER on marginal regions of detected segments,
(b) fragments IR ground truth (data server, registration needed), (c) any
future segmentation. CPU model pipeline still being built — its role is
now sanity-validated map generation for the reader, not virgin-scroll
prediction. Model chosen: `scrollprize/PHerc.1667-iteration-0` (MIT, 334 MB
safetensors, 83M params, pure Conv3d — CPU-safe; recipe: 62 layers, 256 px
tiles, clip [0,200], sigmoid at quarter-res; venv at `~/ink-ml/venv`).

## UPDATE 2026-07-27 — read `findings/overnight2.md` with this

Three things changed that alter how the rest of this document should be read.

1. **The read scroll is in WORSE condition than the unread ones** — 1.28× the
   height noise, 2.86× the correlation length. Segmentation is the difference,
   not preservation. Any plan resting on "the others are too degraded" is
   resting on nothing.

2. **PHerc0172 is blind.** 7.91 µm/voxel = 1.9 voxels through the 15 µm ink
   layer. Its ink was never sampled — and it had been sitting in the TUNE set,
   because the split sorted scroll names alphabetically. It is now a **physics
   control**: anything that correlates there is not measuring ink. Stronger
   than the blank-papyrus control, which argues only from absence of ink.

3. **Both controls are now inside the search objective**, which is the fix the
   previous run demanded:
   ```
   score = heldout_median - 1.5*blank_r - 1.0*max(0, blind_r - 0.05)
   ```
   Confirmed live: `offaxis` scores raw +0.258 (the old swarm would have
   alerted) and 0.209 on blank, so it now scores −0.056 and is walked away
   from.

4. **The first run's negative control was measuring ink.** It picked control
   segments by whole-map coverage (<2%) then scored them through a function
   requiring 5–85% coverage *in the crop*. Those are different numbers — a
   segment can be 99.5% blank while the tested 4×4-chunk window sits on a
   column of text. Every "fires on blank papyrus" verdict was computed on
   crops full of ink. Controls are now verified on the scored crop
   (`pack.crop_coverage`). Re-running those candidates against a correct
   control: they still die (blank 0.12–0.22, not the reported 0.21–0.47, and
   ~0.11 on the blind scroll). **The verdict stands; the evidence for it did
   not.** Never choose a control by whole-map coverage again.

Three more mechanisms tested, three more negatives — RTI specular enhancement,
depth PCA, and letterform matched filtering. **Project total is now twelve.**
Note the deadline discrepancy: this file says July 31, `CLAUDE.md` says the
target is August 31. Nothing is posted either way.

## Where it stands in one paragraph

There is a live, public, cited browser tool for Herculaneum scroll CT
(**https://slice-site-alpha.vercel.app**), a private GitHub repo
(`williamshermer-pixel/slice`), and a Progress Prize submission that has **not
been written or posted**. Deadline **11:59pm Pacific, July 31 2026**. Nine
ink-detection mechanisms were tested against ground truth and all nine failed,
each with a measured reason. Two autonomous search teams are running on the
laptop. No scroll was read.

## The one number that governs everything

**The ink layer is ~15 µm. The unread scrolls were scanned at 8.64 µm — that is
1.7 voxels, below the ~3 needed to resolve a feature at all.** Scroll 1 gets 6.2
voxels through the same layer, which is why it could be read and they cannot.
The ink on those scans is not faint; it was never sampled.

A letter is *enormous* by comparison — 347 voxels tall, 75,000 voxels in area.
Size was never the problem.

## Verified facts (do not re-litigate)

- Bucket is anonymous, `Access-Control-Allow-Origin: *`, verified live.
- Scroll/surface volumes: `chunks [128,128,128]`, `dtype |u1`,
  **`compressor: null`**, `dimension_separator: "/"`. Uncompressed — a chunk is
  a flat 2 MB.
- **Prediction volumes ARE compressed** (blosc/zstd, 192³, ~20:1), so
  `numcodecs` is load-bearing the moment overlays land.
- Volumes are **sparse**: chunks outside the mask were never written; S3 404s and
  zarr fills from `fill_value`. Empty space is free.
- Surface pyramids are **anisotropic** — full depth at every level, only
  in-plane downsampling. `Level` carries `zFactor` separately from `factor`.
  Confusing them clamps a 109-layer sheet to its first 3.
- A surface chunk is `[depth,128,128]` — the whole depth stack of a tile in one
  object. Scrubbing depth is free once cached.
- **255 segments across 7 scrolls have published ink detections** (PHerc. 0139,
  0172, 0343P, 0500P2, 0814, 1667, Paris 4). This is the ground-truth set. Most
  of the session was wasted validating on **one** of them.
- PHerc. 0139's surface volumes are **1.13 µm/voxel** — finer than the ~1 µm
  threshold the morphology literature says the signal needs.

## The scribe's hand (measured off real ink, Scroll 1)

| | |
| --- | --- |
| Line pitch | 6.18 mm |
| Letter height | 3.00 mm |
| Letter advance | 1.86 mm |
| Stroke width | 0.35 mm |

These are baked into the viewer's letter-size box and text check.

## Twelve mechanisms tested, twelve dead

Rows 10-12 were added 2026-07-27; see `findings/overnight2.md` for the detail.

| mechanism | result |
| --- | --- |
| RTI specular enhancement | best +0.056 after controls. Multi-light, normal-unsharp, band-passed — the relief is not in the data |
| Depth PCA (fixed basis) | best +0.070 after controls. PC1 is a sheet-brightness term (0.100 on blank) |
| Letterform matched filter | **median gain −0.046** — matched filtering DESTROYS signal. Correlation lengths 13-45 px, so letters are not independent samples and the area argument does not buy √N |

## The original nine

| mechanism | result |
| --- | --- |
| Density / attenuation | r = **+0.002**, 88% distribution overlap. Carbon on carbon. |
| Surface relief / height | r = 0.139 band-passed; noise floor 30 µm vs 9 µm signal |
| Raking light | r = 0.02 — differentiates away the signal it needs |
| Frequency notch | weave and stroke share a band (335 vs 346 µm) |
| Orientation wedge | +0.016 — real, negligible |
| Letter stacking (√N) | **p = 0.365** — interference is spatially correlated |
| Crack-network geometry | \|d\| < 0.08, below the brightness control |
| Morphological roller (top-hat) | best r = +0.050 after 23 min compute |
| **Crackle to Handmer's spec** | r=+0.368 on the tuned tile, **median +0.013 across held-out** |

That last row is the important one and the cautionary tale: it looked
spectacular (d=0.85, z=+6.18) and was **fitting one sheet's damage pattern**.
`CRITERIA.md` caught it. Read that file before believing any future result.

## What is running right now (as of 2026-07-27 04:00)

**THE DOGS** — 12 workers, `tools/dogs.py`, 10.5-hour budget, started 03:58
local. `caffeinate` is holding the laptop awake.

Search over **19 features** (8 texture + 6 depth-PCA + 5 RTI), tuned on
PHerc0139/0814 (both 13.3 voxels through the ink), scored on 4 held-out
scrolls, with the blank-papyrus control AND the blind-scroll physics control
both subtracted inside the objective.

**Check on waking:**
```bash
ls ~/Desktop/InK/out/dogs/DOGS_ALERT.md          # existence = a ping
tail -30 ~/Desktop/InK/out/dogs/dogs_w0.log
cat ~/Desktop/InK/out/dogs/dogs_best_w*.json | grep penalised
```
An alert now means a candidate scored well on ink while staying quiet on BOTH
blank papyrus and the blind scroll. Nothing in this project has done that yet.
Silence still means the space was mapped and eliminated, which is a result.

Everything below in this section describes the PREVIOUS run, kept for the
record. Its teams are stopped.

Two teams on the laptop, 8-hour budget, started ~00:30 local.

- **Swarm** — 10 workers, `swarm.py`. Random + hill-climb search over feature
  combinations. Tuned on PHerc. 0139/0172, **scored only on the other five
  scrolls**. Fit is never measured, so overfitting cannot win.
- **Forensics** — `forensics.py`. Reads the swarm's logs, picks up anything
  above r=0.18, and attacks it: negative control on blank papyrus, fresh
  held-out tiles, per-scroll breakdown, parameter jitter, evidence render. Every
  test can only kill a candidate, never confirm it.

Best seen so far: **r = +0.312 across 8 held-out segments on 3 scrolls**, using
off-axis orientation alone — but only 38% significant, so it did **not** clear
the bar and no alert fired. The `sharp + offaxis + disorder` family (Handmer's
descriptors) has surfaced independently three times.

**Check on waking:**
```bash
cd /private/tmp/claude-501/-Users-williamshermer-Desktop/61134879-bb6d-4054-8e69-f0e34413bd18/scratchpad
ls FORENSIC_ALERT.md SWARM_ALERT.md 2>/dev/null   # existence = a ping
cat forensics.log | tail -30
ls verdicts/
```
Alert files existing is the only signal that matters. Silence means the search
space was mapped and eliminated — which is itself a result.

**They die if the laptop sleeps.** `caffeinate -i` in an open Terminal keeps it
alive with the screen off.

## THE RESULT THAT MATTERS MOST FROM THE OVERNIGHT RUN

The swarm fired an alert. It was **false**, and the forensic team killed it.

Candidate `offaxis + hfenergy + chandark`: held-out median **r = +0.423** across
8 segments on 3 scrolls, 62% significant. It cleared all four swarm gates.

Then the negative control ran it on **blank papyrus with no ink**: **|r| = 0.281**.

Every high scorer did the same thing:

| candidate | held-out r | on blank papyrus |
| --- | --- | --- |
| offaxis+hfenergy | +0.444 | 0.209 |
| offaxis+hfenergy+disorder | +0.426 | 0.255 |
| offaxis+hfenergy+chandark | +0.423 | 0.281 |
| disorder+offaxis+sharp | +0.230 | 0.466 |
| offaxis alone | +0.182 | 0.421 |

**They are not detecting ink. They are detecting papyrus condition.** Text sits
on well-preserved sheet, so "this sheet looks good" correlates with "there is
text here" without any of it being about ink. Only `chandark` passed the control
(|r|=0.044) and it had too few tiles to finish.

**FIX BEFORE RUNNING THE SWARM AGAIN:** move the negative control INTO the
swarm's own scoring, not after it. A variant's score should be
`heldout_median - penalty * negative_control_r`, evaluated every time. As built,
the swarm optimises straight into the papyrus-detector trap and will keep
producing false alerts forever.

## Next builds, in priority order

**1. PCA across depth (untried, cheap, best idea available).**
Multispectral conservators never look at bands one at a time — they run PCA
across bands to find the combination that maximally separates ink from
substrate. Often no single band shows the text and the third component does.

We have one spectral channel, but **109 depth layers**. Every experiment this
session collapsed depth first — averaged a band, picked the peak, discarded the
rest. Nobody let the data choose which combination of depths carries signal.
Tiles are already cached. No GPU. And the components become new features the
swarm can search over, which breaks the ceiling that it can only recombine the
eight quantities that happened to get written.

**2. RTI-style specular enhancement (William asked for this).**
Reflectance Transformation Imaging is standard on inscriptions: shoot an object
under many light angles, fit a per-pixel model, then relight interactively and
extract normals. The raking-light attempt here was a crude single-angle
Lambertian version. RTI's *specular enhancement* mode is markedly better at
making faint relief legible, and was never implemented. We have full 3D so
normals come free — what is missing is the enhancement and the interactive
relight, which is a display technique, not new information.

**3. TRACERS (William's idea, not yet built)

The third tier after scouts and forensics. The swarm searches *texture*
statistics. Tracers would search for **the writing itself**:

- harvest letterform templates from the published ink maps — the scribe's actual
  24 letters, at known scale, many exemplars each
- fit the baseline grid first (6.18 mm pitch) to collapse the search space
- matched-filter each letter at each grid slot, keep ranked hypotheses
- constrain with Greek: *scriptio continua* means the language model does word
  segmentation as well as letter choice
- **validate by cutting templates from one column and testing on another**

Why it is worth building: a letter is 75,000 voxels. Integrating a weak
per-voxel signal over a known shape is the one argument that survives the
resolution problem. And matched filtering asks an easier question — *"does an
alpha fit here?"* — than *"what is here?"*

The blocker found tonight: stacking failed because the interference is
**spatially correlated**, so √N averaging does not converge. Any tracer design
must confront that, not assume independence.

## The other open lane

**Nobody has chained ink-detection output to a Greek language prior for
Herculaneum.** Verified open territory. Ithaca (DeepMind, Greek, open weights,
epigraphy), Aeneas (2025, Latin), and a Llama-3 fine-tune on papyri.info are all
public. Corpora: papyri.info/DCLP, Diorisis, First1KGreek. **TLG is licensed and
cannot be used for training.** The library is overwhelmingly Philodemus.

No GPU needed. No resolution ceiling. Nobody in it.

## The submission — the thing with a deadline

Nothing is posted. To file:

1. Flip the repo public: `gh repo edit williamshermer-pixel/slice --visibility public`
2. Post in the Vesuvius Discord (William is registered as `willsher`)

What to lead with, in order of how much it makes people stop:
- **the ink-resolution finding** — 1.7 voxels, with the arithmetic
- **coverage vs depth-contrast disagreeing** — the QC table, and that the
  top-ranked-by-coverage segment is unreadable mush
- the tool itself, live and free
- **the nine negatives** — nobody publishes these, and they save others months

Do not overclaim. No letters were read. The credibility of a tool that says
"too weak to call" is the entire asset.

## Where things live

| | |
| --- | --- |
| Source | `~/Desktop/InK` (git repo, remote `williamshermer-pixel/slice`, PRIVATE) |
| Search code | `tools/` — `pack.py` (shared), `dogs.py` (search), `rti.py`, `depth_pca.py`, `tracers.py`, `condition.py` |
| Live run output | `~/Desktop/InK/out/dogs/` — logs, per-worker bests, `DOGS_ALERT.md` |
| Tile cache | `~/.ink-cache` (survives reboots, NOT in git — never commit scroll data) |
| Deploy staging | `~/slice-site` — rsync from source, then `vercel deploy --prod --yes` |
| Live | https://slice-site-alpha.vercel.app |
| Scratch / experiments | `/private/tmp/claude-501/.../scratchpad` (NOT in git, will be lost) |
| Prize rules | https://scrollprize.org/prizes |
| Discord | https://discord.gg/V4fJhvtaQn |

`tools/` holds the reproducible scripts; `findings/` the QC tables;
`CRITERIA.md` the pre-registered standard for what counts as a find.

## Standing rules for whoever picks this up

- **Every finding ships with a render, sent to William for eyes-on review,
  BEFORE it is believed or written up.** (His rule, 2026-07-29, after the
  evidence render killed a fully-controlled false positive twice in one
  night.) Statistics gate; humans verify.

- Never tune and test on the same data. It produced r=+0.368 that meant nothing.
- Every correlation gets a **spatial** null (shift the target, preserve
  autocorrelation). Pixel-permutation nulls are invalid here and will hand you
  p=0.0000 on noise.
- Negative control on blank papyrus, always — and INSIDE the objective, not
  after it. A search climbs whatever gradient you give it.
- Physics control on PHerc0172 (1.9 voxels through the ink). Correlation there
  cannot be ink.
- Check voxels-through-ink before trusting any scroll's role in a split.
  15 µm ÷ (µm/voxel) must be >= 3 or that scan never sampled the ink.
- No generative models on the evidence — ever. They will invent plausible Greek.
- Publishing a negative is a result.
