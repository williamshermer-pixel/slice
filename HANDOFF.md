# HANDOFF — read this first

Session of 2026-07-26/27. Written because context ran out, not because the work
did. Everything below is measured unless flagged otherwise.

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

## Nine mechanisms tested, nine dead

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

## What is running right now

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

## Next build: TRACERS (William's idea, not yet built)

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
| Deploy staging | `~/slice-site` — rsync from source, then `vercel deploy --prod --yes` |
| Live | https://slice-site-alpha.vercel.app |
| Scratch / experiments | `/private/tmp/claude-501/.../scratchpad` (NOT in git, will be lost) |
| Prize rules | https://scrollprize.org/prizes |
| Discord | https://discord.gg/V4fJhvtaQn |

`tools/` holds the reproducible scripts; `findings/` the QC tables;
`CRITERIA.md` the pre-registered standard for what counts as a find.

## Standing rules for whoever picks this up

- Never tune and test on the same data. It produced r=+0.368 that meant nothing.
- Every correlation gets a **spatial** null (shift the target, preserve
  autocorrelation). Pixel-permutation nulls are invalid here and will hand you
  p=0.0000 on noise.
- Negative control on blank papyrus, always.
- No generative models on the evidence — ever. They will invent plausible Greek.
- Publishing a negative is a result.
