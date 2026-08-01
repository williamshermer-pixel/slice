/**
 * Surface volumes — the flattened sheets.
 *
 * This is the catalog that matters for reading text, and it is worth being
 * precise about why, because it is the single easiest thing to get wrong here.
 *
 * A scroll volume is a cylinder of windings. Slicing it axially cuts
 * *perpendicular* through every sheet at once, so you see each sheet edge-on as
 * a thin bright line. Ink is a carbon layer sitting flat on the sheet face, a
 * few tens of microns thick. Edge-on, there is nothing to see. No amount of
 * contrast, colour or zoom recovers a letter from an axial slice — the geometry
 * is wrong, not the settings.
 *
 * A surface volume is that same data after a segment of one sheet has been
 * traced and unwrapped flat. Its axes are:
 *
 *   [layer, y, x]  —  layer = depth THROUGH the sheet, y/x = position ON it
 *
 * So a "slice" of a surface volume is a view of the sheet face, and scrubbing
 * the first axis walks from one side of the papyrus through to the other. The
 * ink sits at a particular depth; finding it is exactly the act of scrubbing
 * layers until the texture resolves. This is where the 2023 First Letters came
 * from and it is the only geometry in which reading is possible.
 *
 * Mechanically these are the same zarr v2 the scroll volumes are — uint8,
 * uncompressed, `dimension_separator: "/"`, multiscale — so `openVolume` and
 * `readSlice` read them unchanged. Verified against live S3.
 *
 * One property is a gift: chunks are [depth, 128, 128], meaning the *entire*
 * depth stack of a tile arrives in a single chunk. Once a tile is cached,
 * scrubbing every layer of it costs nothing at all.
 */

const BUCKET = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com";

export type SurfaceEntry = {
  id: string;
  /** Sample the segment was traced from. */
  scroll: string;
  label: string;
  segment: string;
  url: string;
  voxelUm: number;
  /** [layers, y, x] at level 0. */
  shape: [number, number, number];
  note: string;
};

function surface(scroll: string, segment: string, file: string): string {
  return `${BUCKET}/${scroll}/segments/${segment}/surface-volumes/${file}`;
}

import { build0139 } from "./surfaces.generated";

export const SURFACES: SurfaceEntry[] = [
  {
    id: "Paris4-20231005123336-2.4um",
    scroll: "PHercParis4",
    segment: "20231005123336",
    label: "Scroll 1 · seg 20231005123336 · 2.4 µm",
    url: surface(
      "PHercParis4",
      "20231005123336",
      "2.4um-0.22m-78keV-volume-20260411134726.zarr",
    ),
    voxelUm: 2.4,
    shape: [109, 34880, 97280],
    note: "The segment the 2023 Grand Prize text was read from. Start here — if the tooling cannot show letters on this sheet, it will not show them anywhere.",
  },
  {
    id: "Paris4-20231005123336-45um",
    scroll: "PHercParis4",
    segment: "20231005123336",
    label: "Scroll 1 · seg 20231005123336 · 45.5 µm",
    url: surface(
      "PHercParis4",
      "20231005123336",
      "45.532um-11.0m-74keV-volume-20260310170716.zarr",
    ),
    voxelUm: 45.532,
    shape: [0, 0, 0],
    note: "Coarse scan of the same segment. Useful for finding your way around the sheet before dropping into the 2.4 µm stack.",
  },
];

// The 37 PHerc0139 sheets our cross-scan labels were computed on. Generated
// rather than hand-written (tools/build_surface_catalog.py) because each entry
// needs the volume's real level-0 shape, and a wrong shape here would put the
// viewer somewhere other than where /qc says the disagreement is.
SURFACES.push(...build0139(surface));

export function findSurface(id: string): SurfaceEntry | undefined {
  return SURFACES.find((s) => s.id === id);
}
