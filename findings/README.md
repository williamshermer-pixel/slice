# Findings

Results from scoring the auto-grown segments on the unread scrolls. Produced by
the scripts in [`../tools`](../tools); both are read-only against the public
bucket and need no GPU.

## The short version

**Chunk coverage and depth contrast disagree, and only the second one predicts
whether a segment is readable.**

| | PHerc. 1447 · 20250502205333 | PHerc. 0800 · 20251028213516 |
| --- | --- | --- |
| Claimed area | 3.54 cm² | 1.67 cm² |
| Chunk coverage | **100%** | 100% |
| Coverage rank | **1st** | 10th |
| Depth contrast | **2.61** | **43.45** |
| Rendered result | frayed, fused fibre | clean crossed weave |

Scroll 1's surface volume — the sheet the 2023 Grand Prize text was read from —
scores **≈33** on the same measure. The PHerc. 0800 segment beats it. The
top-ranked-by-coverage segment is unreadable mush.

Triaging on coverage alone points compute at fused papyrus.

## The two measures

**`segment_coverage.json`** — *does the volume actually store data under this
mesh?* For every valid point in a segment's `tifxyz`, work out which chunk of
the raw volume it lands in and ask whether that chunk exists. These volumes are
sparse: chunks lying outside the scroll mask were never written. HEAD requests
only.

Fields: `livefrac` (fraction of valid mesh points sitting on stored chunks),
`live_area` (claimed area × livefrac), `chunks` / `live_chunks`.

**`segment_depth.json`** — *is there a readable sheet there, or fused mush?*
Render a small strip along the surface normal and measure how far the mean
intensity varies through depth. Crossing a real sheet you pass face → interior
→ far face and the profile swings. Inside compressed papyrus it is flat.

Fields: `span` (grey-level range through depth — the score), `filled`,
`thick_um`.

Rough reading of `span`: **≥ 8** a sheet worth rendering · **3–8** marginal ·
**< 3** compressed, no sheet.

## What was found

- **11 segments across two unread scrolls score as genuine sheets**, several
  above Scroll 1's readable surface.
- **PHerc. 0332's two segments are 0% covered** — not renderable at all.
- Claimed area is unreliable on its own: one segment advertises 4.92 cm² and
  delivers 2.88 cm² of backed mesh, then still scores poorly on depth.
- **PHerc. 0800 is underrated.** All its segments are 100% covered and several
  score highly on depth, despite being individually small.

## Caveats

- Depth contrast is sampled from **one small patch per segment** (8×8 grid
  cells, ±12 layers). A segment can be readable in one place and fused in
  another; this is triage, not a survey.
- Four PHerc. 1447 segments report no `area_cm2`, so their real area is unknown
  even where coverage and depth are both good.
- **PHerc. 1203's 22 segments were not scored** — its layout differs and the
  finder did not locate their `tifxyz`. Unfinished, not empty.
- A high depth score means a sheet is *present*, not that ink is present or
  legible. Nothing here claims recovered text.

## Reproducing

```bash
python3 tools/segment_coverage.py   # writes segment_coverage.json
python3 tools/segment_depth.py      # reads it, writes segment_depth.json
```

`volume_metadata.json` and `segments-survey.json` are raw harvests kept for
reference — regenerate rather than trust them if the bucket layout changes.
