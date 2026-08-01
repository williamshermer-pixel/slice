# The seams: read across segment edges, not inside them

*2026-08-01, ~03:00. William's observation, written down the night it was made
because it is the best open lead this project has and it cuts against something
we did deliberately.*

## The observation

Looking at the segments laid out, one butts against the next. It is **one
continuous sheet**, wound. Segments are patches traced out of it separately, so
their boundaries are arbitrary cuts through running text — **words are cut in
half at segment edges.** If half a word sits at the edge of segment A, the other
half is on whichever segment continues it, and the half you can see tells you
what to expect on the other side.

## Why this indicts our own search

Our conjunction search **erodes three letters back from every sheet edge**
(`conjunction_1667.build_search` → `interior()`), and the letter-box requires
95% sheet coverage on top of that. Both were added for a real reason: the
letter-scale high-pass is biased positive within ~3 letters of a boundary in
*both* maps at once, a shared artifact the roll null cannot see, and it
manufactured this project's first false candidate at 0.78 mm from an edge.

The reason is sound and the consequence is that **we systematically excluded the
one place where the text is guaranteed to continue.** We searched the middles of
patches and threw away the joins.

Worse, we had already half-seen it. The handoff's ranked list carried
"wide-field assembly" and it stalled on the note that 0139's segments are
"~30% occupied ribbons with no contiguous column-sized field." That framing was
about making bigger *windows*. The right framing is about **joining
neighbours** — you do not need a contiguous field inside one segment if the
next segment continues the line.

## The data exists, and it is cheap

Every segment publishes its geometry, not just its flattened canvas:

```
PHerc0139/segments/<segment>/mesh/<name>.tifxyz/
    meta.json    bbox in scroll coordinates, scale
    x.tif  y.tif  z.tif    the 3D scroll coordinate of every flattened pixel
```

Verified on `20250108000000-w025_2025010863`:

- three resolutions published (9.362 µm, 2.403 µm, 2.399 µm)
- the coarse one is **340 × 364, float32, 0.5 MB per axis** — 1.5 MB per
  segment, so all 37 segments is about 55 MB
- 100% of its pixels carry a valid coordinate
- `meta.json` gives the bbox directly:
  `[[1924, 2328, 1550], [4227, 4459, 8201]]` in scroll voxels

So the flattened canvas each label sits on can be mapped back into the scroll,
and two segments can be tested for adjacency without downloading a single
volume.

## The test, in order

1. **Bounding boxes first.** Load all 37 `meta.json` files (a few KB total) and
   find which segment bboxes overlap or nearly touch. This alone rules most
   pairs out in seconds.
2. **Edge point clouds.** For each surviving pair, take the boundary pixels of
   each segment's flattened canvas, look up their 3D coordinates, and measure
   the minimum distance between the two clouds. Adjacent-in-the-same-winding
   means *within roughly one sheet thickness*; the next winding out is a whole
   wrap away, which is much further. That distance gap is what makes the test
   clean.
3. **Orientation.** For a genuine pair, find the correspondence along the seam:
   which edge pixel of A maps next to which edge pixel of B.
4. **Read across.** Put the two published ink maps side by side across the
   seam, in the correct orientation, and look. A word cut in half that
   completes across the join is the result — and unlike everything else we
   tried tonight, it is *self-validating*: half a word matching half a word is
   not something a null test has to arbitrate.

## Why this is worth more than the searches we ran

Every negative in this project came from asking "is there faint ink in this
blank region." This asks a different question with a built-in control:
**does the text continue where it must?** The prior is enormous — running text
does not stop at an arbitrary tracing boundary — and the check is visual and
unambiguous.

It also lands directly on the funder's stated bottleneck. Their 2026 Open
Problems page names sheet switches, mesh tracing errors, and "no built-in
connectivity" as the things blocking the unread scrolls, and asks for
"conservative failure detection" and topology-aware tools. A seam-matching test
is exactly that: two segments that *should* join and do not are a tracing error
you have just detected automatically.

## Honest caveats before anyone gets excited

- Adjacent bboxes are necessary, not sufficient. Two patches can be spatially
  close and sit on **different windings**, which is the classic sheet-switch
  error. Step 2's distance gap is what separates those, and it must be measured
  rather than assumed.
- 0139's hand is 1.61 mm and the model's field of view is 578 µm, so its maps
  render letter-sized mass rather than resolved glyphs. Half a *word* completing
  may be visible; half a *letter* completing may not be. Scroll 1's 3.00 mm hand
  would be the better place to prove the method.
- The flattening near a segment edge is the least reliable part of the mesh,
  which is part of why the edges got excluded in the first place. A seam that
  fails to match may be a flattening artifact rather than a real discontinuity.

## Status

Not started. Data verified present and cheap. This is the first thing to pick
up, ahead of rerunning PHerc1667 and PHerc0814 with the corrected instrument.
