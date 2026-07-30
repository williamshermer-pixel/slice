# What this data can and cannot do — measured, 2026-07-27

Written after a voxel-size error cost us a 2x physical-scale mistake across
four scrolls. Everything here is measured against the live bucket, not parsed
from filenames and not inferred from documentation.

## The bucket, surveyed exhaustively

45 samples. 14 have `segments/`. Of those:

| sample | segments | with surface-volumes | with ink-detection |
| --- | --- | --- | --- |
| PHercParis4 | 81 | 60+ | 59+ |
| PHerc0172 | 53 | 53 | 53 |
| PHerc0500P2 | 39 | 39 | 38 |
| PHerc0139 | 38 | 38 | 38 |
| PHerc1667 | 20 | 19 | 19 |
| PHerc0814 | 19 | 19 | 19 |
| PHerc0343P | 8 | 8 | 8 |
| **PHerc1447** | **16** | **4** | **0** |
| PHerc0009B | 20 | 0 | 0 |
| PHercMANBp | 11 | 0 | 0 |
| PHerc0800 | 6 | 0 | 0 |
| PHerc0332 | 2 | 0 | 0 |
| PHerc1203 | 1 | 0 | 0 |
| PHerc1451 | 1 | 0 | 0 |

**CLAUDE.md is stale.** It states "Only PHercParis4 (Scroll 1, already read) has
any [surface volumes]". Seven scrolls now have them, totalling ~240 flattened
segments. The segmentation bottleneck has moved since that was written.

## The three things this data CAN do

1. **Validate a detector across 6 scrolls** — 7 have surface volumes, 6 have
   published ink detections dense enough to score against.
2. **Provide a physics control.** PHerc0172 is 7.91 µm/voxel = 1.9 voxels
   through a 15 µm ink layer. It carries text and published detections, but its
   ink was never sampled. Anything that fires there is not reading ink.
3. **Run blind on PHerc1447.** Four flattened segments, **zero published ink
   detections**. This is the only place in the bucket where a working detector
   could say something nobody has already said.

## The three things it CANNOT do

1. **No real ground truth.** All six detached fragments — `PHercParis2Fr47`,
   `PHerc51Cr4Fr8`, `PHercParis1Fr34`, `PHercParis1Fr39`, `PHercParis2Fr143`,
   `PHerc1667Cr1Fr3` — contain **`photos/` and nothing else**. No CT, no
   infrared labels. The Challenge's own docs say fragments are the ground-truth
   source for ink detection; that data is on Kaggle/scrollprize, not here.
   Every label we validate against is therefore a **CNN's output**.
2. **No reading of the mostly-unread scrolls.** Six samples have segments but
   zero surface volumes — traced but not flattened. Nothing can be read there
   without doing the flattening, which is GPU/VC3D work.
3. **No sub-2 µm detail.** See below.

## THE VOXEL SIZE — the error that forced this document

The surface-volume filenames carry a micron figure, e.g.
`1.129um-0.22m-59keV-volume-...zarr`. **That is the original scan resolution,
not the resolution of the array inside.** The OME metadata is authoritative:

```
multiscales[0].datasets[0].coordinateTransformations -> scale [2.258, 2.258, 2.258]
```

| scroll | filename says | TRUE (level 0) | ratio |
| --- | --- | --- | --- |
| PHerc0139 | 1.129 | **2.258** | 2.00× |
| PHerc0814 | 1.129 | **2.258** | 2.00× |
| PHerc1667 | 1.129 | **2.258** | 2.00× |
| PHercParis4 | 1.129 | **2.258** | 2.00× |
| PHerc0343P | 2.215 | 2.215 | 1.00× |
| PHerc0500P2 | 2.215 | 2.215 | 1.00× |
| PHerc0172 | 7.910 | 7.910 | 1.00× |

**Consequence:** every scale specified in microns — the 350 µm stroke width, the
200–600 µm fibre band, every band-pass and box radius — was converted to a pixel
radius **twice as large as intended** on four of seven scrolls. Features aimed
at a letter stroke were measuring at double that size. This is a plausible
contributor to the negative results and it invalidates the scale settings of
every experiment run before this fix.

`pack.true_um()` now reads the OME metadata and caches it. `targets.json` is
patched. **Never parse a resolution out of a filename again.**

### What it changes downstream

- Voxels through a 15 µm ink layer: PHerc0139 is **6.6**, not 13.3.
  All resolvable scrolls sit at 6.2–6.8. Still above the ~3 threshold, so the
  resolvable/blind split is unchanged — PHerc0172 alone remains blind at 1.9.
- The pyramid is anisotropic as documented: level 1 is `[2.258, 4.516, 4.516]`,
  i.e. depth is never downsampled. Confirmed directly.

## Sheet geometry — RETRACTED 2026-07-27, see below

An earlier version of this section reported "sheet faces" and thicknesses of
41-75 um, located as the steepest intensity gradient either side of the peak,
and concluded the dogs should be aimed at layers -15..-9 and +6..+18.

**That table was wrong and the instruction derived from it is withdrawn.**

Audit (140 cached tiles, full uncropped stacks):

| measurement | value |
| --- | --- |
| median profile FWHM | **162 um** (p25 121, p75 203, p90 261) |
| tiles with FWHM >= 100 um | **83%** |
| tiles falling in the published 41-75 um band | **9%** |
| intensity at the dimmest end of the stack | median **0.74 of peak** (p10 0.44) |
| tiles where BOTH ends exceed 50% of peak | **84%** |
| tiles where the half-max region runs to the stack edge | **68%** |

**There is no papyrus/air boundary anywhere in these surface volumes.** The
stack never reaches air, so a "face" cannot be located by finding where the
material ends. What the old method found were gradient extrema of an *interior
slab*, and 41-75 um was the analysis window, not the sheet: `pack.KEEP=+/-28`
gives a 129 um window (below the true FWHM in 51% of tiles) and `column.py`'s
`span=+/-20` gives 93 um (below FWHM in 59%).

Reproducing the old method on PHerc0139 returns 35-47 um while the same tiles'
true FWHM is 131-167 um — the method reproduces its own answer and not the
sheet.

**What this invalidates:** any depth targeting derived from those layer ranges,
and the "aim at the faces" instruction. The sheet is roughly 162 um thick, which
is normal papyrus (100-300 um), and our analysis windows are narrower than it.

## Depth-column features — a genuinely new class of negative

Built as `tools/column.py` after noticing that ~29 of the project's features
begin with `mid_image()`: a mean over a depth band, producing ONE 2D picture,
with every subsequent operation a 2D texture filter. The project had been
taking a depth-resolved subvolume, discarding the depth, and then hunting for a
surface phenomenon in what remained.

These measure the PROFILE per pixel, with the located surface found per pixel
so sheet warp cannot smear it. AUC with spatial null, 12 held-out tiles.

**Naming caveat (audit, 2026-07-27):** the features are called `shoulder`,
`face` and `thick`, but as established above the stack contains no air and
therefore no sheet boundary. What they actually locate is an **interior
iso-gradient surface** — intensity there is 0.61-0.74 of the column peak, and
9-31% of columns have it pinned at the window edge. The mechanism is sound
(genuinely per-pixel, genuinely unflattened) but the names overclaim. Read the
result as "no profile-shape signature at the located interior surface", NOT as
"no signature at the sheet surface" — the latter was never tested.

| feature | AUC | null | excess | blind |
| --- | --- | --- | --- | --- |
| col_sharp_neg | 0.635 | 0.572 | +0.063 | 0.566 |
| col_rise | 0.634 | 0.574 | +0.060 | 0.553 |
| col_shoulder_neg | 0.622 | 0.563 | +0.060 | 0.558 |
| col_asym | 0.595 | 0.574 | +0.021 | 0.564 |
| col_face_pos | 0.577 | 0.556 | +0.021 | 0.570 |
| col_thick | 0.564 | 0.549 | +0.015 | 0.547 |
| col_shoulder_pos | 0.580 | 0.572 | +0.008 | 0.555 |
| col_face_neg | 0.562 | 0.545 | +0.018 | 0.538 |
| col_sharp_pos | 0.555 | 0.578 | −0.023 | 0.539 |

All below the 0.09 excess bar. The three best all concern the NEGATIVE face —
`sharp_neg`, `rise`, `shoulder_neg` — which is at least consistent with ink
being applied to one side, but the margins are too small to lean on.

This matters as a negative because it is not another texture statistic. It is
the first measurement of profile SHAPE in this project, and it says the ink is
not visible as a shoulder, a face displacement, or a sharpness change at the
sheet surface in these 8-bit surface volumes.

## Performance notes, so they are not rediscovered

- `np.apply_along_axis` over depth runs a Python loop across ~260,000 columns
  per tile: 5.6 s per feature call, unusable in a search. `uniform_filter1d`
  plus a cached per-tile decomposition brings it to 0.12 s.
- `take_along_axis` rather than meshgrid fancy-indexing avoids allocating two
  full-size index arrays per call.
