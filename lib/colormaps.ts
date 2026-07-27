/**
 * Display LUTs.
 *
 * Grayscale is the honest default but it is a poor detector: human vision
 * resolves maybe 30 steps of luminance, and the difference between carbonized
 * papyrus and carbon ink sitting on it is a handful of 8-bit levels. Mapping
 * those levels onto hue instead of brightness makes a density step you cannot
 * see in gray obvious in colour.
 *
 * That is a reading aid, not evidence — a false-colour edge is still just the
 * window you chose. The viewer names the active LUT in the export caption so a
 * shared image can never quietly imply more than the data supports.
 */

export type ColormapId = "graphite" | "ember" | "viridis" | "ice";

export type Colormap = {
  id: ColormapId;
  label: string;
  note: string;
  /** 256 * 3 bytes, RGB. */
  lut: Uint8Array;
};

type Stop = [number, [number, number, number]];

/** Piecewise-linear ramp through control points, sampled to 256 entries. */
function ramp(stops: Stop[]): Uint8Array {
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let a = stops[0];
    let b = stops[stops.length - 1];
    for (let s = 0; s < stops.length - 1; s++) {
      if (t >= stops[s][0] && t <= stops[s + 1][0]) {
        a = stops[s];
        b = stops[s + 1];
        break;
      }
    }
    const span = b[0] - a[0] || 1;
    const k = (t - a[0]) / span;
    lut[i * 3] = Math.round(a[1][0] + (b[1][0] - a[1][0]) * k);
    lut[i * 3 + 1] = Math.round(a[1][1] + (b[1][1] - a[1][1]) * k);
    lut[i * 3 + 2] = Math.round(a[1][2] + (b[1][2] - a[1][2]) * k);
  }
  return lut;
}

export const COLORMAPS: Colormap[] = [
  {
    id: "graphite",
    label: "Graphite",
    note: "Unmodified luminance. What the detector recorded.",
    lut: ramp([
      [0, [0, 0, 0]],
      [1, [255, 255, 255]],
    ]),
  },
  {
    id: "ember",
    label: "Ember",
    note: "Warm ramp. Pulls apart the dense end where sheets touch.",
    lut: ramp([
      [0, [0, 0, 0]],
      [0.25, [58, 20, 18]],
      [0.5, [148, 48, 24]],
      [0.72, [214, 120, 32]],
      [0.88, [240, 190, 110]],
      [1, [255, 250, 238]],
    ]),
  },
  {
    id: "viridis",
    label: "Viridis",
    note: "Perceptually uniform. Equal steps look equal — the honest one.",
    lut: ramp([
      [0, [68, 1, 84]],
      [0.25, [59, 82, 139]],
      [0.5, [33, 145, 140]],
      [0.75, [94, 201, 98]],
      [1, [253, 231, 37]],
    ]),
  },
  {
    id: "ice",
    label: "Ice",
    note: "Cool ramp. Separates the low end where air meets papyrus.",
    lut: ramp([
      [0, [4, 6, 18]],
      [0.35, [22, 62, 110]],
      [0.62, [64, 140, 190]],
      [0.84, [150, 208, 232]],
      [1, [244, 252, 255]],
    ]),
  },
];

export function getColormap(id: ColormapId): Colormap {
  return COLORMAPS.find((c) => c.id === id) ?? COLORMAPS[0];
}

/**
 * Picks a round physical length that fits comfortably inside the view, and
 * returns it both in voxels and as a label.
 *
 * Scroll windings sit roughly 100–300 µm apart, so a scale bar is not
 * decoration here — it is the difference between "those look close" and "those
 * are two sheets".
 */
/**
 * The scribe's hand, measured off the published ink detection for Scroll 1
 * segment 20231005123336: line pitch by autocorrelation of the row projection,
 * letter advance the same way across columns, stroke width by erosion.
 *
 * These are here so the viewer can show you how big a letter actually is. It
 * is startlingly easy to spend an hour tracing shapes that turn out to be seven
 * times letter size — the eye has no scale reference on an unfamiliar texture,
 * and papyrus damage makes handsome curves.
 */
export const HAND = {
  linePitchUm: 6180,
  letterAdvanceUm: 1860,
  letterHeightUm: 3000,
  strokeWidthUm: 346,
  /**
   * Thickness of the ink layer itself. Published SEM gives 3–17 µm and the 2026
   * full-scroll paper reports strokes 10–20 µm; 15 µm is the middle of both.
   *
   * This is the number that decides everything, and it is not the letter size.
   */
  inkLayerUm: 15,
};

export type Resolvability = {
  inkVoxels: number;
  strokeVoxels: number;
  letterVoxels: number;
  verdict: "resolved" | "marginal" | "unresolved";
};

/**
 * Can this scan physically hold the ink?
 *
 * A letter is enormous in voxel terms even on the coarsest scroll — 347 voxels
 * tall at 8.64 µm — and a stroke is 40 voxels wide. Neither is near any limit.
 * The ink *layer* is ~15 µm, which at 8.64 µm sampling is 1.7 voxels. You need
 * roughly three to resolve a feature at all.
 *
 * So on every unread scroll the ink is not faint, it is under-sampled: the scan
 * never recorded it. Scroll 1 gets 6.2 voxels through the same layer, which is
 * why that scroll could be read and these cannot. Saying so plainly saves
 * people from hunting a signal that is not in the file.
 */
export function resolvability(voxelUm: number): Resolvability {
  const inkVoxels = HAND.inkLayerUm / voxelUm;
  return {
    inkVoxels,
    strokeVoxels: HAND.strokeWidthUm / voxelUm,
    letterVoxels: (HAND.letterHeightUm / voxelUm) * (HAND.letterAdvanceUm / voxelUm),
    verdict: inkVoxels >= 3 ? "resolved" : inkVoxels >= 1.5 ? "marginal" : "unresolved",
  };
}

/**
 * Does this look like text? Text sits on evenly spaced baselines, so the row
 * projection of a region containing writing is periodic at the line pitch.
 * Papyrus fibre is periodic too — at about a sixth of that — so the *period*
 * separates them where brightness alone cannot.
 *
 * Returns the strongest periodicity found and whether it falls in the band a
 * line of text would occupy. This is a screen against wishful thinking, not
 * evidence of text: passing it means "not obviously fibre", nothing more.
 */
export type TextVerdict = "consistent" | "wrong-period" | "too-weak";

export function linePitchCheck(
  data: ArrayLike<number>,
  width: number,
  height: number,
  umPerPixel: number,
): { pitchUm: number; strength: number; verdict: TextVerdict } | null {
  if (width < 8 || height < 32) return null;

  // Row means, on values above the midpoint so faint structure still counts.
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < width * height; i += 7) {
    const v = Number(data[i]);
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  const mid = (lo + hi) / 2;
  const prof = new Float64Array(height);
  for (let y = 0; y < height; y++) {
    let s = 0;
    for (let x = 0; x < width; x++) s += Number(data[y * width + x]) > mid ? 1 : 0;
    prof[y] = s / width;
  }
  let mean = 0;
  for (let y = 0; y < height; y++) mean += prof[y];
  mean /= height;
  for (let y = 0; y < height; y++) prof[y] -= mean;

  let zero = 0;
  for (let y = 0; y < height; y++) zero += prof[y] * prof[y];
  if (zero <= 0) return null;

  // Autocorrelation over lags that could plausibly be a line pitch.
  const maxLag = Math.min(height - 2, Math.floor((HAND.linePitchUm * 2.2) / umPerPixel));
  const minLag = Math.max(3, Math.floor((HAND.linePitchUm * 0.25) / umPerPixel));
  if (maxLag <= minLag) return null;

  let bestLag = 0, bestVal = 0;
  for (let lag = minLag; lag <= maxLag; lag++) {
    let s = 0;
    for (let y = 0; y + lag < height; y++) s += prof[y] * prof[y + lag];
    const r = s / zero;
    if (r > bestVal) { bestVal = r; bestLag = lag; }
  }
  if (bestLag === 0) return null;

  const pitchUm = bestLag * umPerPixel;
  // Generous band around the measured hand — scribes vary, and so do scrolls.
  const inBand =
    pitchUm > HAND.linePitchUm * 0.6 && pitchUm < HAND.linePitchUm * 1.6;

  // Three outcomes, not two. A weak correlation at a plausible period is not
  // evidence of fibre — it is no evidence at all, and saying otherwise would
  // make this readout the very thing it exists to guard against.
  const verdict: TextVerdict =
    bestVal < 0.2 ? "too-weak" : inBand ? "consistent" : "wrong-period";
  return { pitchUm, strength: bestVal, verdict };
}

export function scaleBar(
  viewWidthVoxels: number,
  voxelUm: number,
): { voxels: number; label: string; fraction: number } {
  const targetUm = (viewWidthVoxels * voxelUm) / 4;
  const steps = [
    10, 20, 50, 100, 200, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
    100_000,
  ];
  const chosen = steps.find((s) => s >= targetUm) ?? steps[steps.length - 1];
  const voxels = chosen / voxelUm;
  const label =
    chosen >= 1000 ? `${(chosen / 1000).toFixed(chosen % 1000 ? 1 : 0)} mm` : `${chosen} µm`;
  return { voxels, label, fraction: voxels / viewWidthVoxels };
}
