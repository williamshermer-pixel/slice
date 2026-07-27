# Slice

Browser-native viewer for Herculaneum scroll micro-CT volumes. Streams OME-Zarr
chunks straight from the Vesuvius Challenge public S3 bucket — no download, no
credentials, no local install.

Open a URL, drag through a 2,000-year-old carbonized scroll.

## Why this works

The Vesuvius Challenge publishes its volumes as multiscale OME-Zarr in an
anonymous, CORS-open S3 bucket. That combination is unusual and it is the whole
basis of this project. All of it is now confirmed against live S3 rather than
inferred:

- **Anonymous** — no signing, no auth flow, no server holding a key.
- **CORS-open** — the bucket returns `Access-Control-Allow-Origin: *` and
  `Access-Control-Allow-Methods: HEAD, GET` on both metadata and chunks.
- **Chunked and pyramided** — every catalogued volume carries six levels, so a
  window at 32× downsample costs a handful of chunk fetches instead of a
  terabyte.

So the entire read path runs client-side. Vercel serves static assets. There is
no backend in the hot path.

## What the data actually looks like

Read off the bucket, identical across all fourteen catalogued volumes:

```
"chunks": [128, 128, 128]   "dtype": "|u1"   "compressor": null
"dimension_separator": "/"  6 pyramid levels (1× … 32×)
```

Three consequences shape the whole design, and none of them are obvious from
the outside:

**The scroll and surface volumes are uncompressed.** `compressor: null` means no
codec runs when reading them.

That is *not* true of everything in the bucket, and the exception matters: the
surface-prediction volumes under `representations/predictions/surfaces/` are
blosc/zstd with 192³ chunks, and they compress about 20:1 — a chunk is ~340 KB
against 7 MB raw. So `numcodecs` is load-bearing the moment overlays land, and
should not be pruned as an unused dependency on the strength of the scroll
volumes alone.

**A chunk is a flat 2 MB, every time.** 128³ uint8, uncompressed. And chunks
are cubes while the viewer draws a plane, so reading one z-slice still pulls all
128 z-layers of every chunk it touches — a 128× read amplification that no
amount of cropping removes. This is the single most important cost fact about
the project.

**But empty space is free.** The volumes are sparse: a chunk lying entirely
outside the scroll mask is never written, S3 returns 404, and zarr fills it from
`fill_value`. On PHerc. 125 at level 5, a nine-chunk view resolved to four
stored chunks and five absent ones — 8 MB, not 18. The telemetry strip reports
stored and empty separately, because the difference is most of the cost.

## Stack

| Piece | Choice | Note |
| --- | --- | --- |
| Framework | Next.js 15, App Router | Static export works too |
| Zarr | `zarrita` 0.7.3 | v2 + v3, tree-shakeable |
| Codecs | `numcodecs` 0.3.2 | Not exercised by these volumes — see above |
| Styling | Tailwind v4 | CSS-first config in `app/globals.css` |

## Run it

```bash
npm install
```

```bash
npm run dev
```

Deploy: push to GitHub, import into Vercel, accept the defaults. There is
nothing to configure — no environment variables, no secrets.

## Layout

```
lib/zarr.ts       Streaming core: open multiscale, windowed slice reads,
                  chunk cache, fetch telemetry, grayscale rendering
lib/volumes.ts    Catalog — 13 scrolls eligible for the 2027 Grand Prize,
                  plus PHerc. 332, the one that has been read
components/       The viewer UI
app/api/chunk/    Fallback S3 proxy (unused; see below)
```

### `lib/zarr.ts` is the part that matters

Everything else is replaceable. Four things in here are worth knowing about:

**Windowed reads.** `readSlice` takes a crop box, not a whole slice. A full
level-0 slice of a scroll volume spans thousands of chunks and will hang the
tab. The UI keeps its view box in level-0 coordinates and divides by the level
factor, so switching resolution preserves what you are looking at.

**Auto display window.** These volumes are masked and masked-out voxels are
exactly 0. On a real level-4 chunk that is 26% of the data — far more than the
0.5% the low percentile is meant to discard — so including zeros pins the low
end at 0 and yields `[0, 136]` instead of `[54, 138]`. Two fifths of the
available contrast, spent rendering empty air. `autoWindow` drops the mask value
before taking percentiles.

**Chunk cache.** S3 sends an ETag and a Last-Modified but **no Cache-Control**,
so browser reuse falls back to heuristic freshness — not something to build a
pan gesture on at 2 MB a chunk. An LRU with a 256 MB budget holds them instead.
Moving the z slider within a chunk band is then genuinely free: measured at 15
chunks / 30 MB served from memory, zero new bytes.

**Fetch telemetry.** The store is wrapped in a `Proxy` that counts every chunk
request, byte, cache hit and absent chunk, keeping metadata reads out of the
chunk count. The readout under the canvas is not decoration — it is how you tell
a 4-chunk read from a 400-chunk one before you commit to it.

### The proxy route is deliberately unused

`app/api/chunk/[...path]` proxies S3 through Vercel's edge cache. Nothing calls
it. It exists because open CORS is a policy rather than a guarantee: if that
ever changes, repoint `openVolume` at `/api/chunk/...` and the app keeps
working. Cheap insurance, zero cost while unused.

## State of things

Verified against live S3, July 2026:

- **Cross-origin chunk streaming works.** PHerc. 125 renders in the browser from
  14 metadata reads and 9 chunk requests. This was the project's one open
  question and it is now answered.
- `lib/` typechecks clean under `strict`; `next build` is clean.
- All 14 catalogued volumes return 200 on `.zattrs`, carry a well-formed OME
  `multiscales` attribute, and expose 6 levels of uncompressed 128³ uint8.
  The numbered-subgroup fallback in `openVolume` is therefore genuinely a
  fallback.
- Shared links restore scroll, level, slice and crop.

Corrected along the way:

- **PHerc. 332's URL was dead.** The transcribed 2023 path 404s; the volume is
  now a December 2025 rescan at 2.399 µm, found by listing `PHerc0332/volumes/`
  (the bucket permits anonymous listing).
- **The cost estimate under-quoted unaligned views.** `ceil(width / chunk)`
  assumes a chunk-aligned box; a 300-voxel span starting at 350 covers four
  chunk columns, not three. It now counts the chunk span, so the bound holds.

## Where the letters are

Worth stating plainly, because it decides what is worth building.

**A raw scroll volume cannot show a letter.** Slicing a cylinder of windings
axially cuts perpendicular through every sheet at once, so each sheet appears
edge-on as a thin bright line. Ink is a carbon layer lying flat on the sheet
face; edge-on there is nothing to see, at any contrast or zoom. That is
geometry, not settings.

**A surface volume can.** Once a sheet has been traced and unwrapped flat its
axes become `[layer, y, x]` — depth *through* the sheet, position *on* it — so a
slice is a view of the sheet face and scrubbing layers walks through the
papyrus. This is the geometry the 2023 First Letters came from. Mechanically
they are the same zarr, so `openVolume`/`readSlice` read them unchanged: the
viewer's "Sheets" mode is the same code path with a different URL.

Checked exhaustively across the bucket: **only Scroll 1 (PHercParis4, already
read) has surface volumes.** All thirteen unread scrolls carry
`segments/<id>/mesh/` and nothing flattened. So the bottleneck for the unread
scrolls is segmentation — mesh to flattened sheet — not ink detection.

Two storage facts shape the tooling. Surface pyramids are **anisotropic**: they
keep every sheet layer at every level and only downsample in-plane, so `Level`
carries `zFactor` separately from `factor` (using one for the other clamps a
109-layer sheet to its first three). And a surface chunk is `[depth, 128, 128]`
— the whole depth stack of a tile in one object — so fetching a tile once makes
every layer of it free. The lab's depth contact sheet drew 55 layers for 10.2 MB
of network against 551.8 MB served from cache.

## Where this could go

1. ~~**Shareable coordinates.**~~ Done — specimen, level, depth, crop and LUT
   live in the query string.
2. ~~**Surface volumes.**~~ Done — the "Sheets" source.
3. **Ink labelling.** Scrub depth layers, paint ink/no-ink, export a mask.
   Ground truth is a stated bottleneck.
4. **Overlays.** Published ink-detection output (`ink-detection/*.tif`) and
   surface predictions (`representations/predictions/surfaces/*.zarr`, present
   on all 14 samples) share dimensions with the source. Alpha-blend them.

Anonymous bucket listing works, so specimen discovery could replace the
hardcoded catalog entirely — which would also have caught the PHerc. 332
breakage.

## The lab

`/lab` is password-gated and holds the depth contact sheet: every layer of a
tile at once, for finding the depth the ink sits at. The public viewer is
deliberately not gated.

The gate is server-enforced in `middleware.ts` — the passphrase never reaches
the client bundle, and the cookie holds a SHA-256 of it rather than the value,
httpOnly. It **fails closed**: with no `LAB_PASSWORD` set, the lab is
unreachable rather than open, so a deploy that forgets the variable locks
instead of publishing. Set it in `.env.local` locally (see `.env.example`) and
in the deployment's environment variables.

It is one shared passphrase for a private bench, not per-user auth. If it ever
needs to distinguish people, it needs real sessions.

## Licence and citation

Code: MIT. Progress Prize submissions must be open-sourced under a permissive
licence to accept an award, so this is the right default from commit one.

Scroll data: CC BY-NC 4.0, © Vesuvius Challenge. This repo redistributes none
of it — it only points a browser at the public bucket.

Scroll 1 (`PHercParis4`), which this project leans on heavily, is part of the
legacy **EduceLab-Scrolls** dataset, © EduceLab / University of Kentucky:

> Parsons, S., Parker, C. S., Chapman, C., Hayashida, M., & Seales, W. B.
> (2023). *EduceLab-Scrolls: Verifiable Recovery of Text from Herculaneum
> Papyri using X-ray CT*. ArXiv [Cs.CV]. https://doi.org/10.48550/arXiv.2304.02084

Full attribution, including the scan-data citation and the non-commercial terms
that come with CC BY-NC 4.0, is in [CITATION.md](CITATION.md) and is shown in
the app footer rather than only in a file.
