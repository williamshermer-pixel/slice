# CLAUDE.md

Context for Claude Code working in this repo. Read this before proposing changes.

## What this is

A browser-native viewer for micro-CT volumes of carbonized Herculaneum scrolls,
streaming OME-Zarr chunks directly from the Vesuvius Challenge public S3 bucket.
No download, no credentials, no backend in the read path.

It is a **foundation, not a finished submission**. See "Goal" below.

## Goal

The owner is targeting a Vesuvius Challenge **Progress Prize**. These run
monthly, deadline 11:59pm Pacific on the last day of each month. The best
submission is guaranteed $20,000; tiers below are $10,000, $2,500 and $1,000.
Multiple awards per month are permitted.

Target: the **August 31, 2026** deadline.

Judging criteria, which should shape technical decisions:

1. **Released early.** Shipping in-progress work beats a polished late reveal.
2. **Actually gets used.** They watch for bug reports and feature requests, and
   their Annotation Team comments publicly on tools they use. This is the
   highest-weight criterion and the one most under our control.
3. **Solves a real problem** from their published wishlist.
4. **Well documented.**

Consequence for planning: prefer shipping a narrow thing this week over a broad
thing next month. Optimise for someone else opening the URL and using it.

Requirements: submissions must be **open-sourced under a permissive licence**
(MIT here) to accept an award, and the owner must be in the project Discord.

## The wishlist is the spec

Do not invent features. Work comes from GitHub issues on `ScrollPrize/villa`
labelled `help wanted` — in that repo the label's description is literally
"Good candidate for a Progress Prize". The `good first issue` label marks the
newcomer subset.

`https://github.com/ScrollPrize/villa/issues?q=is:issue+state:open+label:"help wanted"`

**Triage heuristic.** For any candidate issue, ask what the output artifact is:

- A view, label, annotation, shareable link, format conversion, or QC dashboard
  → browser problem. In scope.
- A trained checkpoint, mesh, segmentation, or a metric on a benchmark → GPU or
  C++/VC3D problem. Out of scope for this repo.

Words that mean out of scope: model, loss, training, nnUNet, mesh growing,
spiral fitting. Words that mean in scope: annotate, inspect, convert,
visualize, compare.

Worked example: issue #191, "Surface and Fiber Predictions in Compressed or
Highly Curved areas", is nnUNetv2 residual encoder UNets with medial surface
loss. No amount of frontend work touches it.

Calibration on the entry tier: a recent $1,000 award went to a utility that
converted fiber annotations from NML into CSV/JSON/SWC and reported basic
statistics. That is the bar for $1,000. Small, useful, documented.

## Why the architecture works

The data is unusually well suited to browser streaming, and this is the whole
technical thesis:

- The bucket is **anonymous** — no signing, no auth, so no server needs a key.
- It is **CORS-open**. Verified indirectly: the official prize page links each
  scroll to a Neuroglancer instance loading
  `zarr2://https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/...`
  cross-origin in a browser tab.
- Volumes are **8-bit, chunked 128³, with a multiscale pyramid**, so a 512×512
  window at 8× downsample costs a handful of chunk fetches.

Therefore: static Next.js on Vercel, all reads client-side, no backend.

## Stack and verified facts

| Piece | Version | Note |
| --- | --- | --- |
| Next.js | ^15.3 | App Router |
| zarrita | ^0.7.3 | v2 + v3 support |
| numcodecs | ^0.3.2 | required, but see below |
| Tailwind | ^4 | CSS-first config, no `tailwind.config.ts` |

**Verified by inspecting installed source, do not re-litigate:**

- zarrita 0.7.3's default codec registry already maps `blosc`, `zstd`, `lz4`,
  `gzip`, `zlib` plus the `numcodecs.*` v2-compat aliases. **No manual
  `registry.set()` call is needed.** `numcodecs` only needs to be installed so
  zarrita's dynamic `import("numcodecs/blosc")` resolves.
- zarrita's public API here: `FetchStore`, `open`, `get`, `slice`, `registry`,
  `root`, `Array`, `Group`.
- `lib/` typechecks clean under `strict`; `next build` is clean.

**Verified against live S3, July 2026 — do not re-litigate:**

- **Cross-origin chunk streaming works.** PHerc. 125 renders in the browser from
  14 metadata reads and 9 chunk requests. The bucket returns
  `Access-Control-Allow-Origin: *` on metadata and chunks alike. The proxy route
  stays unused.
- **All 14 volumes** return 200 on `.zattrs`, carry a well-formed OME
  `multiscales` attribute, and expose **6 levels** (1×–32×). The
  numbered-subgroup fallback in `openVolume` is genuinely a fallback.
- **Uniform storage:** `chunks [128,128,128]`, `dtype |u1`,
  **`compressor: null`**, `dimension_separator: "/"`. Scroll and surface volumes
  are *uncompressed*, so no codec runs when reading them.
- **But predictions are compressed.** `representations/predictions/surfaces/*.zarr`
  is blosc/zstd, 192³ chunks, ~20:1 (a chunk is ~340 KB against 7 MB raw), same
  6-level pyramid and **the same shape as the raw volume it belongs to**, so it
  aligns voxel-for-voxel and can be alpha-blended directly. Present on all 14
  samples including the unread ones. **`numcodecs` is therefore load-bearing the
  moment overlays land** — do not prune it after looking only at scroll volumes.
- **A chunk is a flat 2 MB**, and a slice pulls all 128 z-layers of every chunk
  it touches — a 128× read amplification cropping cannot remove.
- **The volumes are sparse.** Chunks entirely outside the mask were never
  written; S3 404s and zarr fills from `fill_value`. PHerc. 125 level 5: a
  nine-chunk view is four stored + five absent, 8 MB not 18. Empty space is
  free, and the telemetry reports the two separately.
- **Anonymous bucket listing works** (`?list-type=2&prefix=…&delimiter=/`),
  which is how the dead PHerc. 332 URL was repaired and how volume discovery
  could eventually replace the hardcoded catalog.

**Fixed, with the reasoning, so it is not undone:**

- `autoWindow` excluded nothing, and the mask is exactly 0 — 26% of a real
  level-4 chunk. That pinned the low end at 0 and gave `[0,136]` instead of
  `[54,138]`. It now drops zeros before taking percentiles.
- `readCost` used `ceil(width / chunk)`, which assumes a chunk-aligned box. A
  300-voxel span starting at 350 covers four chunk columns, not three, so the
  bound did not hold. It now counts the chunk span.
- Panning committed the view box on every `pointermove`, queueing a 2 MB read
  per mouse event. Pan is now CSS-only until pointer-up, and every read is
  debounced.
- The z slider runs in level-0 coordinates, so at 32× thirty-two positions named
  one physical slice and each refetched identical data. Reads are keyed on
  `snapZ`.
- Read failures set `error` but the overlay only renders when `status !==
  "ready"`, so they were invisible. They now surface under the telemetry.

## Where the letters are — read this before proposing any feature

The goal is reading the text. The geometry decides what is possible, and this
is the easiest thing in the project to get wrong.

**A raw scroll volume cannot show a letter.** Slicing a cylinder of windings
axially cuts perpendicular through every sheet at once, so each sheet appears
edge-on as a thin bright line. Ink is a carbon layer lying flat on the sheet
face. Edge-on there is nothing to see, at any contrast, colour or zoom. This is
geometry, not settings. Do not build features that promise otherwise.

**A surface volume can.** Once a sheet is traced and unwrapped flat, its axes
become `[layer, y, x]` — layer is depth *through* the sheet, y/x are position
*on* it. A slice is then a view of the sheet face, and scrubbing layers walks
through the papyrus. This is the geometry the 2023 First Letters came from.

Verified in the bucket, July 2026:

- Surface volumes live at
  `<sample>/segments/<segid>/surface-volumes/*.zarr`, and are the same zarr v2
  the scroll volumes are — uint8, uncompressed, `dimension_separator: "/"`,
  multiscale. `openVolume`/`readSlice` read them unchanged.
- **Only PHercParis4 (Scroll 1, already read) has any.** All thirteen unread
  scrolls carry `segments/<id>/mesh/` and nothing flattened. Checked
  exhaustively across every segment of every sample that has one.
- Every sample has `representations/predictions/surfaces/*.zarr` — model output
  marking where sheet surfaces are, not flattened sheets.

**So the bottleneck for the unread scrolls is segmentation — mesh → flattened
surface volume — not ink detection.** That gap is why they are unread, and any
plan that skips it is a plan to look at pretty cross-sections.

Two storage facts that shape the tooling:

- Surface pyramids are **anisotropic**: they keep every sheet layer at every
  level and only downsample in-plane. `Level` therefore carries both `factor`
  and `zFactor`, and depth must use `zFactor`. Using `factor` for depth clamps
  a 109-layer sheet to its first 3 layers, silently.
- A surface chunk is `[depth, 128, 128]` — the **whole depth stack of a tile in
  one object**. Fetch a tile once and every layer of it is free. Measured: 55
  layers rendered for 10.2 MB of network and 551.8 MB served from cache. The
  depth contact sheet in `/lab` exists because of this property.

## Layout

```
lib/zarr.ts              Streaming core — the part that matters
lib/volumes.ts           Catalog: 13 Grand-Prize-eligible scrolls + PHerc. 332
components/SliceViewer.tsx   Viewer UI
app/api/chunk/[...path]/ Fallback S3 proxy, deliberately unused
catalog-metadata.json    Harvested .zarray/.zattrs facts for all 14 volumes.
                         Reference only, not imported — regenerate rather than
                         trust it if the bucket layout changes.
```

### `lib/zarr.ts`

Four deliberate decisions worth preserving:

- **Windowed reads.** `readSlice` takes a crop box. A full level-0 slice spans
  thousands of chunks and will hang the tab. The UI stores its view box in
  level-0 coordinates and divides by `level.factor`, so switching resolution
  preserves the view.
- **Percentile auto-window, mask excluded.** Volumes are masked and mostly air;
  naive min/max stretch renders near-black mush, and so does a percentile that
  counts the zeros.
- **Chunk cache.** An LRU with a 256 MB budget, because S3 sends no
  `Cache-Control` and a chunk is 2 MB. This is what makes scrubbing z within a
  chunk band free.
- **Fetch telemetry.** The store is wrapped in a `Proxy` counting every chunk,
  byte, cache hit and absent chunk, with metadata reads kept out of the chunk
  count. The readout under the canvas is load-bearing, not decoration — it
  distinguishes a 6-chunk read from a 600-chunk one before you commit.

### The proxy route

`app/api/chunk/[...path]` proxies S3 through Vercel's edge cache and is
currently called by nothing. Keep it. Open CORS is a policy, not a guarantee;
if it changes, repointing `openVolume` is a one-line fix.

## Design conventions

**Named concept: PLATE & LEDGER.** Two registers held apart on purpose. The
*plate* is a scientific atlas figure — the slice inside a ruled frame with
registration crosses at the corners and an engraved caption below it. The
*ledger* is the machine half — hairline-ruled rows, uppercase micro labels,
numerals hard right so a changing digit is visible in peripheral vision.

Nothing is rounded and nothing is a card. A conservation bench is flat, ruled
and labelled, and the only thing on it allowed to be beautiful is the specimen.

Palette is carbonized papyrus, defined as Tailwind v4 `@theme` tokens in
`app/globals.css`:

`void #0a0a0b` · `panel #131316` · `rule #26262b` · `ash #8b8b94` ·
`papyrus #e9e5db` · `ochre #c8971f`

Ochre is the only accent, reserved for live or interactive state. The CT slice
is the only element permitted to be bright white.

**Type: two faces, no sans.** Instrument Serif for display — masthead, plate
captions, the large telemetry figures. JetBrains Mono for the entire interface.
The chrome is a readout rather than an app, so the mono *is* the UI voice; that
is the deliberate risk in this design and it should not be softened by adding a
sans back in.

Primary choices (source, colour ramp) are always visible labelled buttons.
Popovers and dropdowns are for secondary parameters only.

Copy style: plain verbs, sentence case, no filler. Errors say what happened and
what to do. Do not add marketing language.

## Roadmap, in priority order

1. ~~**Shareable URL coordinates.**~~ **Done.** `?v=&l=&z=&x=&y=&w=&h=`, written
   with `router.replace` on a 300 ms debounce so a pan gesture does not fill the
   back button, and read once at mount so it never fights live input.
2. **Surface volumes.** Segments carry `surface-volumes/*.zarr`, the flattened
   layer stacks ink models consume. Same code path, different URL.
3. **Ink labelling.** Scrub depth layers, paint ink/no-ink, export a mask.
   Ground truth is a stated project bottleneck.
4. **Prediction overlays.** Published ink-detection and surface-prediction
   outputs are zarr with matching dimensions. Alpha-blend them.

## Constraints

- **Never commit scroll data.** It is CC BY-NC 4.0, © Vesuvius Challenge. This
  repo points a browser at the public bucket and redistributes nothing.
- **No GPU work on Vercel.** Serverless, seconds of compute. Training and
  volume processing belong on Modal or RunPod, with Vercel as front end.
- Keep the read path client-side. Adding a backend forfeits the main advantage.
- Do not add dependencies without reason; `zarrita` + `numcodecs` is the whole
  data stack and should stay that way.

## Deployment

Push to GitHub, import at vercel.com/new, accept defaults. No environment
variables, no secrets, nothing to configure.
