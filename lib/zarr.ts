import * as zarr from "zarrita";

/**
 * Streaming access to Vesuvius Challenge OME-Zarr volumes.
 *
 * The volumes live in a public, anonymous S3 bucket served with
 * `Access-Control-Allow-Origin: *`, so the browser reads chunks directly — no
 * backend, no credentials, no download. Verified against live S3, July 2026.
 *
 * Two properties of the real data drive everything below, both confirmed by
 * reading `.zarray` off the bucket rather than by assumption. All fourteen
 * catalogued volumes agree:
 *
 *   "chunks": [128, 128, 128]   "dtype": "|u1"   "compressor": null
 *
 * `compressor: null` means these volumes are **uncompressed**. No codec runs on
 * this path, so a chunk is a flat 128^3 = 2,097,152 bytes on the wire — every
 * time. And because chunks are cubes while the viewer draws a plane, reading
 * one z-slice still pulls all 128 z-layers of every chunk it touches: a 128x
 * read amplification that no amount of cropping removes.
 *
 * That is the entire cost model, and it is why the cache and the telemetry
 * below are load-bearing rather than decorative.
 */

/** Uncompressed 128^3 uint8. Not a guess — read off the bucket. */
export const CHUNK_BYTES = 128 * 128 * 128;

export type FetchStats = {
  /** Chunk fetches that returned data. Metadata reads are counted separately. */
  requests: number;
  bytes: number;
  networkMs: number;
  /** Chunk reads served from memory, i.e. requests that cost nothing. */
  hits: number;
  hitBytes: number;
  /**
   * Chunks that are not stored at all. These volumes are sparse: a chunk lying
   * entirely outside the scroll mask is never written, S3 returns 404, and zarr
   * fills it from `fill_value`. Measured on PHerc. 125 level 5, a nine-chunk
   * view resolved to four stored chunks and five absent ones — 8 MB, not 18.
   * Empty space is free, which is the single best property this data has.
   */
  absent: number;
  /** `.zarray` / `.zattrs` / `.zgroup` reads. Small, and not chunk traffic. */
  metadata: number;
  /** Requests currently in flight. Internal to the wall-clock accounting. */
  inFlight: number;
  /** When the current burst of concurrent requests began. */
  burstStart: number;
};

export function newStats(): FetchStats {
  return {
    requests: 0,
    bytes: 0,
    networkMs: 0,
    hits: 0,
    hitBytes: 0,
    absent: 0,
    metadata: 0,
    inFlight: 0,
    burstStart: 0,
  };
}

/** Metadata keys end in a zarr sidecar name; chunk keys end in an index. */
function isMetadataKey(key: string): boolean {
  return /\.z(array|attrs|group)$|zarr\.json$/.test(key);
}

/**
 * Least-recently-used chunk cache with a byte budget.
 *
 * S3 returns these chunks with an ETag and a Last-Modified but **no
 * Cache-Control**, so browser reuse falls back to heuristic freshness — which
 * is implementation-defined and not something to build a pan gesture on. At
 * 2 MB a chunk, re-fetching on every drag is the difference between a viewer
 * and a bandwidth incident. So we hold them ourselves.
 */
class ChunkCache {
  private entries = new Map<string, Uint8Array>();
  private bytes = 0;

  constructor(private readonly budget: number) {}

  get(key: string): Uint8Array | undefined {
    const hit = this.entries.get(key);
    if (hit === undefined) return undefined;
    // Re-insert to mark most-recently-used.
    this.entries.delete(key);
    this.entries.set(key, hit);
    return hit;
  }

  set(key: string, value: Uint8Array): void {
    if (this.entries.has(key)) return;
    this.entries.set(key, value);
    this.bytes += value.byteLength;
    while (this.bytes > this.budget && this.entries.size > 1) {
      const oldest = this.entries.keys().next();
      if (oldest.done) break;
      const evicted = this.entries.get(oldest.value);
      this.entries.delete(oldest.value);
      this.bytes -= evicted?.byteLength ?? 0;
    }
  }
}

/** ~128 chunks resident. Enough to pan a window without re-paying for it. */
const CACHE_BUDGET = 256 * 1024 * 1024;

/**
 * Wraps a store so every chunk fetch is counted and memoised. zarrita's
 * `Readable` interface only requires `get`, so this thin proxy is enough — and
 * the numbers it collects are the whole point of the telemetry strip in the UI.
 */
function instrument<S extends { get: (...args: never[]) => unknown }>(
  store: S,
  stats: FetchStats,
  cache: ChunkCache,
): S {
  return new Proxy(store, {
    get(target, prop, receiver) {
      const value = Reflect.get(target, prop, receiver);
      if (prop !== "get" || typeof value !== "function") return value;
      return async (...args: unknown[]) => {
        const key = typeof args[0] === "string" ? args[0] : null;
        const isChunk = key !== null && !isMetadataKey(key);

        if (isChunk) {
          const hit = cache.get(key);
          if (hit !== undefined) {
            stats.hits += 1;
            stats.hitBytes += hit.byteLength;
            return hit;
          }
        }

        // Wall clock, not the sum of durations. zarrita fetches a view's chunks
        // concurrently, so adding each request's elapsed time reported half an
        // hour of "network" for a ten-second load. What matters is how long at
        // least one request was outstanding, so time is only counted while the
        // in-flight count is above zero.
        if (stats.inFlight === 0) stats.burstStart = performance.now();
        stats.inFlight += 1;
        let result: unknown;
        try {
          result = await (value as (...a: unknown[]) => unknown).apply(target, args);
        } finally {
          stats.inFlight -= 1;
          if (stats.inFlight === 0) {
            stats.networkMs += performance.now() - stats.burstStart;
          }
        }

        if (!isChunk) {
          stats.metadata += 1;
        } else if (result instanceof Uint8Array) {
          stats.requests += 1;
          stats.bytes += result.byteLength;
          cache.set(key, result);
        } else {
          // 404 — this chunk is outside the mask and was never stored.
          stats.absent += 1;
        }
        return result;
      };
    },
  }) as S;
}

export type Level = {
  /** Path within the zarr group, e.g. "0" for full resolution. */
  path: string;
  /** [z, y, x] */
  shape: number[];
  /** [z, y, x] */
  chunks: number[];
  dtype: string;
  /** In-plane downsample factor relative to level 0, e.g. 4 means 4x smaller. */
  factor: number;
  /**
   * Downsample factor along the depth axis, which is NOT always `factor`.
   *
   * Scroll pyramids are isotropic, so both are 32 at level 5. Surface volumes
   * are not: they keep every one of their ~109 sheet layers at every level and
   * only shrink in-plane. Reusing `factor` for depth there silently clamps the
   * reachable layers to the first three of a hundred and nine — which is most
   * of the sheet, including wherever the ink is.
   */
  zFactor: number;
  array: zarr.Array<zarr.DataType, zarr.Readable>;
};

export type Volume = {
  url: string;
  levels: Level[];
};

/**
 * Opens a multiscale volume. Reads the OME `multiscales` attribute to find the
 * pyramid levels; if the attribute is missing or malformed, falls back to
 * probing numbered subgroups.
 *
 * The attribute is present and well-formed on all fourteen catalogued volumes
 * — each carries exactly six levels — so the fallback is genuinely a fallback.
 * It costs nothing to keep.
 */
export async function openVolume(
  url: string,
  stats: FetchStats,
  signal?: AbortSignal,
): Promise<Volume> {
  const store = instrument(
    new zarr.FetchStore(url),
    stats,
    new ChunkCache(CACHE_BUDGET),
  );
  const group = await zarr.open(store, { kind: "group", signal });

  const paths = readMultiscalePaths(group.attrs) ?? ["0", "1", "2", "3", "4", "5"];

  const levels: Level[] = [];
  for (const path of paths) {
    try {
      const array = await zarr.open(group.resolve(path), { kind: "array", signal });
      if (array.shape.length !== 3) continue;
      levels.push({
        path,
        shape: [...array.shape],
        chunks: [...array.chunks],
        dtype: String(array.dtype),
        factor: 1,
        zFactor: 1,
        array,
      });
    } catch {
      // A missing level just means the pyramid is shorter than we probed for.
    }
  }

  if (levels.length === 0) {
    throw new Error(
      `No 3D arrays found at ${url}. Check that the URL points at the .zarr root.`,
    );
  }

  const base = levels[0].shape[2];
  const baseDepth = levels[0].shape[0];
  for (const level of levels) {
    level.factor = Math.max(1, Math.round(base / level.shape[2]));
    level.zFactor = Math.max(1, Math.round(baseDepth / level.shape[0]));
  }

  return { url, levels };
}

function readMultiscalePaths(attrs: unknown): string[] | null {
  if (typeof attrs !== "object" || attrs === null) return null;
  const multiscales = (attrs as Record<string, unknown>).multiscales;
  if (!Array.isArray(multiscales) || multiscales.length === 0) return null;
  const datasets = (multiscales[0] as Record<string, unknown>)?.datasets;
  if (!Array.isArray(datasets)) return null;
  const paths = datasets
    .map((d) => (d as Record<string, unknown>)?.path)
    .filter((p): p is string => typeof p === "string");
  return paths.length > 0 ? paths : null;
}

/**
 * The worst case a read can cost, before you commit to it.
 *
 * Chunks are cubes and a slice is a plane, so the z axis contributes a full
 * chunk depth no matter how thin the crop is. Reporting bytes rather than a
 * bare chunk count is the difference between "12 chunks" (sounds free) and
 * "25 MB" (is not).
 *
 * This is an upper bound, not an estimate, and often a generous one: the
 * volumes are sparse, so any chunk lying entirely outside the mask costs a 404
 * instead of 2 MB. Bounding high is the right direction for a warning — better
 * to over-quote a read than to talk someone into hanging their tab.
 */
export function readCost(
  level: Level,
  box: { x: number; y: number; width: number; height: number },
): { chunks: number; bytes: number } {
  const [, chunkY, chunkX] = level.chunks;
  const [, height, width] = level.shape;
  const f = level.factor;

  // Where the box actually lands matters, not just how big it is: a 300-voxel
  // span starting at 350 covers chunk columns 2..5 — four of them, where
  // `ceil(300 / 128)` would have promised three. Counting the span instead of
  // the size is the difference between a bound that holds and one that doesn't.
  const span = (start: number, size: number, limit: number, chunk: number) => {
    const a = clamp(Math.round(start / f), 0, limit - 1);
    const b = clamp(a + Math.round(size / f), a + 1, limit);
    return Math.floor((b - 1) / chunk) - Math.floor(a / chunk) + 1;
  };

  const chunks =
    span(box.x, box.width, width, chunkX) * span(box.y, box.height, height, chunkY);
  return { chunks, bytes: chunks * CHUNK_BYTES };
}

/**
 * Snaps a level-0 z to the nearest voxel this level can actually resolve.
 *
 * The z slider runs in level-0 coordinates so the view survives level switches,
 * but at 16x downsample sixteen consecutive slider positions all name the same
 * physical slice. Without snapping, each of those is a fresh read of identical
 * data. With it, the slider is free until it crosses a real boundary.
 */
/**
 * A centred opening view that costs no more than `budgetBytes`.
 *
 * Fitting the whole extent is the obvious default and it is wrong for surface
 * volumes: their chunks carry the entire depth stack, so the coarsest level of
 * a flattened sheet is 216 chunks — 364 MB — where the same gesture on a scroll
 * costs 9. Opening a specimen should never be able to spend that before the
 * user has asked for anything, so the initial crop shrinks until it fits.
 *
 * Returned in level-0 coordinates, matching the view box the UI holds.
 */
export function fitBudget(
  level: Level,
  budgetBytes: number,
): { x: number; y: number; width: number; height: number } {
  const f = level.factor;
  const fullW = level.shape[2] * f;
  const fullH = level.shape[1] * f;
  let box = { x: 0, y: 0, width: fullW, height: fullH };

  // Halve about the centre until the bound fits. Bounded at ~2^12 shrinks.
  for (let i = 0; i < 12; i++) {
    if (readCost(level, box).bytes <= budgetBytes) break;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const width = Math.max(level.chunks[2] * f, box.width / 2);
    const height = Math.max(level.chunks[1] * f, box.height / 2);
    box = { x: cx - width / 2, y: cy - height / 2, width, height };
  }
  return box;
}

export function snapZ(level: Level, z: number): number {
  const maxIndex = level.shape[0] - 1;
  return clamp(Math.round(z / level.zFactor), 0, maxIndex);
}

export type Region = {
  data: ArrayLike<number>;
  width: number;
  height: number;
  /** Origin of this crop in *this level's* voxel coordinates. */
  x0: number;
  y0: number;
  /** Slice index within this level. */
  z: number;
  decodeMs: number;
};

/**
 * Reads one axial slice, cropped to a window. Cropping matters: a full slice at
 * level 0 of a scroll volume spans thousands of chunks, which is a very
 * effective way to hang a browser tab.
 *
 * `zIndex` indexes *this level* and is expected to be already snapped — see
 * `snapZ`.
 */
export async function readSlice(
  level: Level,
  zIndex: number,
  box: { x: number; y: number; width: number; height: number },
  signal?: AbortSignal,
): Promise<Region> {
  const [depth, height, width] = level.shape;
  const zi = clamp(Math.round(zIndex), 0, depth - 1);
  const x0 = clamp(Math.round(box.x), 0, width - 1);
  const y0 = clamp(Math.round(box.y), 0, height - 1);
  const x1 = clamp(x0 + Math.round(box.width), x0 + 1, width);
  const y1 = clamp(y0 + Math.round(box.height), y0 + 1, height);

  const started = performance.now();
  const region = await zarr.get(
    level.array,
    [zi, zarr.slice(y0, y1), zarr.slice(x0, x1)],
    { signal },
  );
  return {
    data: region.data as unknown as ArrayLike<number>,
    width: region.shape[1],
    height: region.shape[0],
    x0,
    y0,
    z: zi,
    decodeMs: performance.now() - started,
  };
}

/**
 * 256-bin histogram of the visible crop, with the mask excluded for the same
 * reason `autoWindow` excludes it: a bin at zero holding a quarter of the
 * voxels flattens everything else to nothing.
 */
export function histogram(data: ArrayLike<number>): { bins: number[]; peak: number } {
  const bins = new Array<number>(256).fill(0);
  const stride = Math.max(1, Math.floor(data.length / 60000));
  for (let i = 0; i < data.length; i += stride) {
    const v = Number(data[i]);
    if (v !== 0) bins[v & 255] += 1;
  }
  return { bins, peak: Math.max(1, ...bins) };
}

/**
 * Samples a straight line between two points in region coordinates.
 *
 * This is the ink-hunting instrument. Sheets of papyrus read as a regular train
 * of density peaks; where the train breaks, stalls, or doubles, something is
 * happening — a delamination, a fold, or two windings pressed into one. The eye
 * is bad at judging that across a noisy grayscale field and a plot is not.
 */
export function lineProfile(
  region: Region,
  from: { x: number; y: number },
  to: { x: number; y: number },
  samples = 240,
): number[] {
  const out: number[] = [];
  for (let i = 0; i < samples; i++) {
    const t = samples === 1 ? 0 : i / (samples - 1);
    const x = Math.round(from.x + (to.x - from.x) * t);
    const y = Math.round(from.y + (to.y - from.y) * t);
    if (x < 0 || y < 0 || x >= region.width || y >= region.height) {
      out.push(0);
      continue;
    }
    out.push(Number(region.data[y * region.width + x]));
  }
  return out;
}

/**
 * Picks display bounds from the data itself, ignoring the long tail at both
 * ends — and ignoring the mask.
 *
 * These volumes are masked, and masked-out voxels are exactly `fill_value`, 0.
 * On a real level-4 chunk from PHerc. 125 that is 26% of the voxels, far more
 * than the 0.5% the low percentile is meant to discard: including zeros pins
 * the low end at 0 and the window comes out [0, 136] instead of [54, 138]. Two
 * fifths of the available contrast, spent rendering empty air. So the mask
 * value is excluded before the percentiles are taken.
 */
export function autoWindow(
  data: ArrayLike<number>,
  loPercentile = 0.5,
  hiPercentile = 99.5,
): [number, number] {
  const stride = Math.max(1, Math.floor(data.length / 20000));
  const sample: number[] = [];
  for (let i = 0; i < data.length; i += stride) {
    const v = Number(data[i]);
    if (v !== 0) sample.push(v);
  }
  // An all-mask crop has nothing to stretch. Full range beats dividing by zero.
  if (sample.length === 0) return [0, 255];
  sample.sort((a, b) => a - b);
  const at = (p: number) =>
    sample[clamp(Math.floor((p / 100) * (sample.length - 1)), 0, sample.length - 1)];
  const lo = at(loPercentile);
  const hi = at(hiPercentile);
  return hi > lo ? [lo, hi] : [lo, lo + 1];
}

/**
 * Maps raw voxel values through a display window and a LUT.
 *
 * `lut` is 256*3 RGB. Passing the identity grayscale ramp reproduces the
 * original behaviour exactly, so colour is opt-in rather than imposed.
 */
export function toImageData(
  region: Region,
  lo: number,
  hi: number,
  lut?: Uint8Array,
): ImageData {
  const { data, width, height } = region;
  const out = new Uint8ClampedArray(width * height * 4);
  const span = hi - lo || 1;
  for (let i = 0; i < width * height; i++) {
    const v = clamp(((Number(data[i]) - lo) / span) * 255, 0, 255) | 0;
    const o = i * 4;
    if (lut) {
      out[o] = lut[v * 3];
      out[o + 1] = lut[v * 3 + 1];
      out[o + 2] = lut[v * 3 + 2];
    } else {
      out[o] = v;
      out[o + 1] = v;
      out[o + 2] = v;
    }
    out[o + 3] = 255;
  }
  return new ImageData(out, width, height);
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
