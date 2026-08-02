"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  autoWindow,
  fitBudget,
  formatBytes,
  histogram,
  lineProfile,
  newStats,
  openVolume,
  readCost,
  readSlice,
  snapZ,
  toImageData,
  type FetchStats,
  type Level,
  type Region,
  type Volume,
} from "@/lib/zarr";
import { VOLUMES, findVolume } from "@/lib/volumes";
import { SURFACES, findSurface } from "@/lib/surfaces";
import {
  COLORMAPS,
  getColormap,
  scaleBar,
  linePitchCheck,
  resolvability,
  HAND,
  handFor,
  INK_BAND,
  type ColormapId,
} from "@/lib/colormaps";
import { exportPng } from "@/lib/export";
import { encodeGrayTiff, downloadBlob } from "@/lib/tiff";
import {
  loadInkCatalog,
  sheetForVolume,
  topDecile,
  type InkSheet,
} from "@/lib/inkmaps";

type ViewBox = { x: number; y: number; width: number; height: number };
type Source = "scroll" | "sheet";

const READ_DEBOUNCE_MS = 140;
const COST_WARN_BYTES = 96 * 1024 * 1024;
/** Ceiling on the first read after opening a specimen. */
const OPEN_BUDGET_BYTES = 64 * 1024 * 1024;

/** One catalog shape for both kinds of volume, so the UI has a single path. */
type Specimen = {
  id: string;
  label: string;
  url: string;
  voxelUm: number;
  shape: [number, number, number];
  note: string;
  /** Which scroll (scribe) this belongs to — hands are NOT shared. */
  scroll?: string;
};

function specimensFor(source: Source): Specimen[] {
  return source === "scroll"
    ? VOLUMES.map((v) => ({
        id: v.id,
        label: v.label,
        url: v.url,
        voxelUm: v.voxelUm,
        shape: v.shape,
        note: v.unread ? "Unread. No text has ever been recovered." : "Text recovered 2023.",
        scroll: v.id,
      }))
    : SURFACES.map((s) => ({
        id: s.id,
        label: s.label,
        url: s.url,
        voxelUm: s.voxelUm,
        shape: s.shape,
        note: s.note,
        scroll: s.scroll,
      }));
}

export default function SliceViewer() {
  const router = useRouter();
  const params = useSearchParams();
  const seed = useRef(readUrlState(params)).current;

  /**
   * Default to the sheet where the overlay is UNAMBIGUOUS.
   *
   * Two earlier defaults were wrong in the same way. PHerc. 125 raw is a
   * cross-section in which letters cannot appear at all by geometry, so a first
   * visit showed a grey blob. A PHerc0139 sheet is better — it has labels — but
   * 0139 writes a 1.61 mm hand against a model field of view of 578 µm, so its
   * overlay is letter-sized mass rather than letterforms, and a first visit
   * showed blobs that read as a broken tool.
   *
   * Scroll 1's control segment is the one sheet in the library with a 3.00 mm
   * hand, and it is where the overlay was verified landing on letterform-shaped
   * marks on baselines. Land there: if the first thing a stranger sees is
   * ambiguous, everything after it reads as ambiguous too.
   */
  const DEFAULT_SOURCE: Source = "sheet";
  const DEFAULT_SPECIMEN = "Paris4-20231005123336-2.4um";
  const [source] = useState<Source>("sheet");
  const [specimenId, setSpecimenId] = useState(
    seed.specimenId ??
      (findSurface(DEFAULT_SPECIMEN)
        ? DEFAULT_SPECIMEN
        : specimensFor(seed.source ?? DEFAULT_SOURCE)[0].id),
  );

  const [volume, setVolume] = useState<Volume | null>(null);
  const [status, setStatus] = useState<"idle" | "opening" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [readError, setReadError] = useState<string | null>(null);

  const [levelIndex, setLevelIndex] = useState(0);
  const [z, setZ] = useState(0);
  const [box, setBox] = useState<ViewBox | null>(null);

  const [window_, setWindow] = useState<[number, number]>([0, 255]);
  const [autoLevels, setAutoLevels] = useState(true);
  const [colormap, setColormap] = useState<ColormapId>(seed.colormap ?? "graphite");

  const [region, setRegion] = useState<Region | null>(null);
  const [reading, setReading] = useState(false);
  const [stats, setStats] = useState<FetchStats>(newStats);
  const [copied, setCopied] = useState(false);

  const [cursor, setCursor] = useState<{ vx: number; vy: number; value: number } | null>(null);
  const [profile, setProfile] = useState<number[] | null>(null);
  const [profileMode, setProfileMode] = useState(false);

  /**
   * Labelling frame.
   *
   * Painting is locked to the crop and level it started in. The failure mode
   * this avoids is the one the project calls its primary bottleneck: labels
   * that drift off the surface they describe. If the view could pan or change
   * resolution mid-session the mask would silently resample under the strokes,
   * and a label that no longer means what it meant when drawn is worse than no
   * label at all. So the frame is fixed and only the depth axis moves — which
   * is also exactly the gesture, since finding the layer the ink sits on IS the
   * work.
   */
  const [labelFrame, setLabelFrame] = useState<{
    levelIndex: number;
    box: ViewBox;
    width: number;
    height: number;
  } | null>(null);
  const masksRef = useRef<Map<number, Uint8Array>>(new Map());
  const [maskVersion, setMaskVersion] = useState(0);
  const [brush, setBrush] = useState(4);
  const [erasing, setErasing] = useState(false);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);

  /**
   * Ink overlay.
   *
   * The map is written on this surface volume's own canvas, so a map pixel maps
   * to the sheet by a pure scale and the overlay needs no registration. The
   * scale is measured per sheet (`canvas[0] / image.width`), never assumed: the
   * true factor is 8.0006, and baking 8 drifts the overlay about a letter width
   * across a 30,000-pixel sheet.
   *
   * Verified at pixel level on Scroll 1, where the overlay lands on
   * letterform-shaped marks sitting on baselines.
   */
  const [showLabels, setShowLabels] = useState(true);
  const [labelAlpha, setLabelAlpha] = useState(0.55);
  /**
   * The recoloured overlay is cached. Rebuilding it inside the paint effect
   * meant recolouring up to 2M pixels on every pan, zoom, window and colormap
   * change, which made the overlay visibly lag in and out. It depends only on
   * the raster and the threshold, so it is rebuilt only when those change.
   */
  const labelCanvas = useRef<HTMLCanvasElement | null>(null);
  /** Surface level-0 px per overlay px. Measured, not assumed. */
  const labelScaleRef = useRef<number | null>(null);
  /** The raw published scores, kept so the threshold can move without refetching. */
  const inkRawRef = useRef<ImageData | null>(null);
  /** Always changes when a raster is (un)loaded, so the paint effect re-runs
   *  even when two sheets happen to share a scale factor. */
  const [labelVersion, setLabelVersion] = useState(0);
  const [labelSeg, setLabelSeg] = useState<string | null>(null);
  const [labelKind, setLabelKind] =
    useState<"cross-scan" | "published" | null>(null);
  /**
   * Which model's map, when a sheet carries more than one. PHerc0172 is the
   * reason this exists: two checkpoints ran on the same volume, so switching
   * between them shows model-vs-model disagreement rather than energy-vs-energy.
   */
  const [inkSheet, setInkSheet] = useState<InkSheet | null>(null);
  const [mapIndex, setMapIndex] = useState(0);
  /**
   * Score cutoff, 0–255. Defaults to the top decile of the sheet's own non-zero
   * scores, which is the cutoff the Scroll 1 positive control passed at.
   *
   * The point of making it movable: these maps are continuous, not binarised —
   * 244 distinct values on the sheet I measured. Everything below a publication
   * cutoff is real model output that nobody looks at, and telling "no ink" from
   * "no ink recovered yet" is an open problem in their own docs. Lowering this
   * is how you see the difference. It is also how you fool yourself, so the
   * readout always says how far below the default you have gone.
   */
  const [inkThreshold, setInkThreshold] = useState<number | null>(null);
  const [inkDefault, setInkDefault] = useState<number | null>(null);
  const statsRef = useRef<FetchStats>(newStats());

  const catalog = useMemo(() => specimensFor(source), [source]);
  const specimen = catalog.find((s) => s.id === specimenId) ?? catalog[0];
  const level: Level | null = volume?.levels[levelIndex] ?? null;
  const base = volume?.levels[0] ?? null;
  const volumeRef = useRef<typeof volume>(null);
  useEffect(() => {
    volumeRef.current = volume;
  }, [volume]);
  const depthLabel = source === "sheet" ? "layer" : "slice z";

  // Open whenever the specimen changes.
  useEffect(() => {
    const controller = new AbortController();
    const target = specimensFor(source).find((s) => s.id === specimenId) ?? specimensFor(source)[0];
    setStatus("opening");
    setError(null);
    setReadError(null);
    setVolume(null);
    setRegion(null);
    setProfile(null);
    statsRef.current = newStats();
    setStats({ ...statsRef.current });

    openVolume(target.url, statsRef.current, controller.signal)
      .then((opened) => {
        if (controller.signal.aborted) return;
        const baseLevel = opened.levels[0];
        const s = seed.applied ? null : seed;
        seed.applied = true;

        const startLevel = clampInt(
          s?.level ?? opened.levels.length - 1,
          0,
          opened.levels.length - 1,
        );
        setVolume(opened);
        setLevelIndex(startLevel);
        setZ(s?.z ?? Math.floor(baseLevel.shape[0] / 2));
        // Never spend more than this before the user has asked for anything.
        setBox(s?.box ?? fitBudget(opened.levels[startLevel], OPEN_BUDGET_BYTES));
        setAutoLevels(true);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setStatus("error");
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => controller.abort();
  }, [source, specimenId, seed]);

  const zIndex = level ? snapZ(level, z) : 0;

  const [committed, setCommitted] = useState<{ z: number; box: ViewBox } | null>(null);
  useEffect(() => {
    if (!box) return;
    const t = setTimeout(() => setCommitted({ z: zIndex, box }), READ_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [zIndex, box]);

  useEffect(() => {
    if (!level || !committed) return;
    const controller = new AbortController();
    setReading(true);
    setReadError(null);

    const f = level.factor;
    const { box: view, z: zi } = committed;
    readSlice(
      level,
      zi,
      { x: view.x / f, y: view.y / f, width: view.width / f, height: view.height / f },
      controller.signal,
    )
      .then((next) => {
        if (controller.signal.aborted) return;
        setRegion(next);
        setStats({ ...statsRef.current });
        setReading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setReading(false);
        setStats({ ...statsRef.current });
        setReadError(err instanceof Error ? err.message : String(err));
      });

    return () => controller.abort();
  }, [level, committed]);

  useEffect(() => {
    if (autoLevels && region) setWindow(autoWindow(region.data));
  }, [autoLevels, region]);

  /**
   * Which overlays exist for this sheet.
   *
   *   published   Vesuvius Challenge's own ink detection, read straight from
   *               their bucket. 367 sheets across 7 scrolls. Continuous scores,
   *               so the cutoff is a control rather than a constant.
   *   cross-scan  ours — PHerc0139 only, 37 segments with maps at two energies,
   *               so the raster carries agree / disagree / silent.
   *
   * Published is the default wherever it exists, because it is the thing being
   * shown; cross-scan is a second opinion on top of it.
   */
  const [hasCrossScan, setHasCrossScan] = useState(false);
  useEffect(() => {
    setInkSheet(null);
    setHasCrossScan(false);
    setMapIndex(0);
    setInkThreshold(null);
    setInkDefault(null);
    if (source !== "sheet" || !specimen) return;
    let cancelled = false;
    loadInkCatalog().then((cat) => {
      if (cancelled) return;
      setInkSheet(sheetForVolume(cat, specimen.url) ?? null);
    });
    const seg = specimenId.startsWith("0139-")
      ? specimenId.slice("0139-".length)
      : null;
    if (seg) {
      fetch("/qc/index.json")
        .then((r) => r.json())
        .then((d: { segments: { segment: string }[] }) => {
          if (!cancelled) {
            setHasCrossScan(d.segments.some((x) => x.segment === seg));
          }
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [specimenId, source, specimen]);

  /** Default to theirs when it exists, ours when it does not. */
  useEffect(() => {
    setLabelKind(inkSheet ? "published" : hasCrossScan ? "cross-scan" : null);
  }, [inkSheet, hasCrossScan]);

  // Fetch the raster for the selected overlay and hold it un-thresholded.
  useEffect(() => {
    labelCanvas.current = null;
    labelScaleRef.current = null;
    inkRawRef.current = null;
    setLabelSeg(null);
    setLabelVersion((v) => v + 1);
    if (source !== "sheet" || !labelKind) return;
    let cancelled = false;

    const map =
      labelKind === "published" ? inkSheet?.maps[mapIndex] : undefined;
    const seg =
      labelKind === "published"
        ? inkSheet?.segment
        : specimenId.slice("0139-".length);
    const url =
      labelKind === "published" ? map?.url : `/qc/${seg}.png`;
    if (!url || !seg) return;

    const img = new Image();
    // Their bucket sends `Access-Control-Allow-Origin: *`, but a canvas read of
    // a cross-origin image taints it unless the request is explicitly CORS.
    // Without this, getImageData throws and the overlay silently never appears.
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      const off = document.createElement("canvas");
      off.width = img.width;
      off.height = img.height;
      const oc = off.getContext("2d", { willReadFrequently: true });
      if (!oc) return;
      oc.drawImage(img, 0, 0);
      const px = oc.getImageData(0, 0, img.width, img.height);
      inkRawRef.current = px;
      // Measured, not assumed. For their maps the sheet's canvas width is known
      // from the volume metadata; for our cross-scan PNGs the raster is written
      // on the same canvas, so the same division holds.
      const canvasX = inkSheet?.canvas?.[0] ?? specimen.shape[2];
      labelScaleRef.current = canvasX / img.width;
      if (labelKind === "published") {
        const d = topDecile(px.data);
        setInkDefault(d);
        setInkThreshold(d);
      }
      setLabelSeg(seg);
      setLabelVersion((v) => v + 1);
    };
    img.src = url;
    return () => {
      cancelled = true;
    };
  }, [labelKind, inkSheet, mapIndex, specimenId, source, specimen]);

  /**
   * Recolour at the current cutoff.
   *
   * Split from the fetch so moving the threshold does not refetch a 570 KB map,
   * and split from the paint effect so panning does not recolour 2M pixels.
   */
  useEffect(() => {
    const px = inkRawRef.current;
    if (!px) return;
    const out = new ImageData(
      new Uint8ClampedArray(px.data),
      px.width,
      px.height,
    );
    const d = out.data;
    if (labelKind === "cross-scan") {
      // Our raster stores a CODE in red (0 unlabelled / 1 ink / 2 blank /
      // 3 disputed) and a downsample-safe disputed flag in green.
      for (let p = 0; p < d.length; p += 4) {
        const code = d[p];
        const disputed = d[p + 1] > 127;
        if (code === 1) {
          d[p] = 233; d[p + 1] = 229; d[p + 2] = 219; d[p + 3] = 255;
        } else if (code === 3 || disputed) {
          d[p] = 200; d[p + 1] = 151; d[p + 2] = 31; d[p + 3] = 255;
        } else {
          d[p + 3] = 0;
        }
      }
    } else {
      // Their raster is a continuous score. At or above the cutoff reads as
      // papyrus white; below the default cutoff but above the current one reads
      // ochre, so relaxing the threshold shows you exactly what you added
      // rather than quietly enlarging the white.
      const t = inkThreshold ?? 255;
      const base = inkDefault ?? t;
      for (let p = 0; p < d.length; p += 4) {
        const v = d[p];
        if (v >= base) {
          d[p] = 233; d[p + 1] = 229; d[p + 2] = 219; d[p + 3] = 255;
        } else if (v >= t) {
          d[p] = 200; d[p + 1] = 151; d[p + 2] = 31; d[p + 3] = 255;
        } else {
          d[p + 3] = 0;
        }
      }
    }
    const off = document.createElement("canvas");
    off.width = px.width;
    off.height = px.height;
    const oc = off.getContext("2d");
    if (!oc) return;
    oc.putImageData(out, 0, 0);
    labelCanvas.current = off;
    setLabelVersion((v) => v + 1);
  }, [labelKind, inkThreshold, inkDefault, labelSeg]);

  // Paint.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !region) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = region.width;
    canvas.height = region.height;
    ctx.putImageData(
      toImageData(region, window_[0], window_[1], getColormap(colormap).lut),
      0,
      0,
    );

    // Label overlay, composited from the pre-recoloured canvas. Source rect is
    // a pure scale: the ink map is written on this volume's own canvas, so
    // there is nothing to register.
    const lc = labelCanvas.current;
    const f = labelScaleRef.current; // surface level-0 px per overlay px
    if (!showLabels || !lc || !f || !box) return;
    const sx = box.x / f;
    const sy = box.y / f;
    const sw = box.width / f;
    const sh = box.height / f;
    if (sw <= 0 || sh <= 0) return;

    /**
     * How far the ds8 overlay is being stretched: destination pixels per
     * overlay pixel. Below 1 it is shrinking, above 1 it is being magnified
     * past its own resolution. Both fixes below key off this.
     */
    const scale = sw > 0 ? region.width / sw : 1;

    /**
     * Knock the papyrus back before drawing ink on it, harder the closer you get.
     *
     * Without any dimming the overlay is invisible in practice: a CT slice of
     * Scroll 1 is near-white and extremely busy, and the ink is drawn in
     * papyrus white — the same value as the loudest thing underneath.
     *
     * A FIXED dim is then wrong at one end. At a wide field the CT is soft
     * texture and 62% is plenty. Zoomed in, the viewer switches to a finer
     * pyramid level and the fibre weave becomes high-contrast detail at the
     * same spatial frequency as the letters, so the ink needs more separation.
     * Ramp 0.62 -> 0.80 as the overlay is magnified.
     *
     * Dimming the base rather than brightening the ink keeps the design rule
     * that the specimen is the only bright thing: the papyrus stays the
     * specimen, it just steps back to substrate while ink is on top.
     */
    const dim = Math.min(0.8, 0.62 + 0.06 * Math.max(0, Math.log2(scale)));
    ctx.save();
    ctx.fillStyle = `rgba(10, 10, 11, ${dim.toFixed(3)})`;
    ctx.fillRect(0, 0, region.width, region.height);
    ctx.restore();

    /**
     * Smooth the overlay only when it is being MAGNIFIED past its resolution.
     *
     * Zoomed out the overlay is downscaled and nearest-neighbour is right: it
     * keeps calls crisp and invents no ink between pixels. Zoomed in,
     * nearest-neighbour shatters letterforms into hard 8-pixel blocks exactly
     * as the CT underneath sharpens — so letters that are unmistakable on the
     * whole sheet dissolve as you go closer, which is backwards from what
     * zooming is for.
     *
     * Interpolating a known-coarse source is honest smoothing, not fabricated
     * detail: the readout still reports the map as ds8 and the note under the
     * control still says treat the overlay as regional, not exact.
     */
    ctx.save();
    ctx.globalAlpha = labelAlpha;
    ctx.imageSmoothingEnabled = scale > 1;
    if (scale > 1) ctx.imageSmoothingQuality = "high";
    ctx.drawImage(lc, sx, sy, sw, sh, 0, 0, region.width, region.height);
    ctx.restore();
  }, [region, window_, colormap, showLabels, labelAlpha, labelVersion, box]);

  // Mirror the view into the URL.
  useEffect(() => {
    if (status !== "ready" || !box || !level) return;
    const t = setTimeout(() => {
      const q = new URLSearchParams({
        src: source,
        v: specimenId,
        l: String(levelIndex),
        z: String(Math.round(z)),
        x: String(Math.round(box.x)),
        y: String(Math.round(box.y)),
        w: String(Math.round(box.width)),
        h: String(Math.round(box.height)),
        c: colormap,
      });
      router.replace(`?${q.toString()}`, { scroll: false });
    }, 300);
    return () => clearTimeout(t);
  }, [status, source, specimenId, levelIndex, z, box, level, colormap, router]);

  /**
   * Keyboard.
   *
   *   up / down     depth — the axis you scrub to find ink. Ink on these
   *                 sheets lies in layers 27-89 of 116 (measured: reading the
   *                 stack centre instead of that band cost AUC 0.654 vs 0.944
   *                 against published calls), so this is the control that
   *                 matters most.
   *   left / right  pan across the sheet
   *   drag          pan freely
   *   + -           zoom, 0 fits the sheet
   *
   * Shift multiplies by ten on depth and pans a whole view.
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) return;
      if (!base || !level) return;

      // Depth steps by one *resolvable* layer: the depth factor, not the
      // in-plane one — they differ on surface volumes.
      const zStep = (e.shiftKey ? 10 : 1) * level.zFactor;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        return setZ((v) => clampInt(v + zStep, 0, base.shape[0] - 1));
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        return setZ((v) => clampInt(v - zStep, 0, base.shape[0] - 1));
      }
      if (e.key === "+" || e.key === "=") return zoom(0.5);
      if (e.key === "-") return zoom(2);
      if (e.key === "0") {
        e.preventDefault();
        return setBox({ x: 0, y: 0, width: base.shape[2], height: base.shape[1] });
      }
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const dir = e.key === "ArrowRight" ? 1 : -1;
      setBox((cur) => {
        if (!cur) return cur;
        const frac = e.shiftKey ? 1 : 1 / 3;
        const nx = cur.x + dir * cur.width * frac;
        return { ...cur, x: Math.max(0, Math.min(nx, base.shape[2] - cur.width)) };
      });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, level]);

  const cost = useMemo(
    () => (level && box ? readCost(level, box) : { chunks: 0, bytes: 0 }),
    [level, box],
  );

  const hist = useMemo(() => (region ? histogram(region.data) : null), [region]);

  const bar = useMemo(
    () => (box ? scaleBar(box.width, specimen.voxelUm) : null),
    [box, specimen.voxelUm],
  );

  /** How big a letter is, in canvas fractions, for the on-screen reference. */
  const hand = useMemo(() => handFor(specimen.scroll), [specimen.scroll]);
  const letterScale = useMemo(() => {
    if (!box || box.width <= 0) return null;
    const viewUm = box.width * specimen.voxelUm;
    return {
      w: hand.letterAdvanceUm / viewUm,
      h: hand.letterHeightUm / (box.height * specimen.voxelUm),
      tooSmallToSee: hand.letterAdvanceUm / viewUm < 0.004,
    };
  }, [box, specimen.voxelUm]);

  /** Screen against wishful thinking: is the current view periodic like text? */
  const textCheck = useMemo(() => {
    if (!region || !level) return null;
    const umPerPixel = specimen.voxelUm * level.factor;
    const spanUm = region.height * umPerPixel;
    // Needs at least a couple of line pitches in frame or the answer is noise.
    if (spanUm < hand.linePitchUm * 2.5) {
      return { tooShort: true, needMm: (hand.linePitchUm * 2.5) / 1000 } as const;
    }
    const r = linePitchCheck(region.data, region.width, region.height, umPerPixel);
    return r ? ({ tooShort: false, ...r } as const) : null;
  }, [region, level, specimen.voxelUm]);

  /** Can this scan physically hold the ink? Decided by voxel size alone. */
  const res = useMemo(() => resolvability(specimen.voxelUm), [specimen.voxelUm]);

  const paintedLayerCount = useMemo(() => {
    void maskVersion; // recount whenever a stroke lands
    let n = 0;
    for (const m of masksRef.current.values()) if (m.some((v) => v !== 0)) n += 1;
    return n;
  }, [maskVersion]);

  const zoom = useCallback(
    (factor: number, anchor?: [number, number]) => {
      setBox((current) => {
        if (!current || !base) return current;
        // Anchor: 0..1 across the current view. 0.5,0.5 is the centre; the
        // wheel and double-click pass the cursor so the thing under the
        // pointer stays under the pointer, which is the whole of what makes a
        // map feel controllable.
        const ax = anchor ? anchor[0] : 0.5;
        const ay = anchor ? anchor[1] : 0.5;
        const px = current.x + current.width * ax;
        const py = current.y + current.height * ay;
        /**
         * Scale BOTH axes by one factor.
         *
         * This used to clamp width and height independently against the sheet,
         * which quietly destroyed the aspect ratio: Scroll 1 is 97280 x 34880,
         * so zooming out pinned the height at 34880 while the width kept
         * doubling, and every further click stretched the view into a longer
         * letterbox. That is what "Out is crazy" was — not a dead button, a
         * button that deformed the picture a little more each press.
         *
         * So the clamp is a single scalar applied to both axes. The box shape
         * is invariant under zoom; only its size changes.
         */
        let width = current.width * factor;
        let height = current.height * factor;
        /**
         * Zooming out ends at the whole sheet, not at a wall.
         *
         * Clamping the scalar instead would freeze the box the moment its
         * FIRST axis saturated — on a 1400x1160 sheet a 2:1 view sticks at
         * 1400 wide with 460 rows it can never reach, and Out becomes a button
         * that does nothing. Since the canvas letterboxes now, a box that does
         * not match the plate's shape costs nothing, so the honest terminal
         * state is the sheet itself.
         */
        if (width >= base.shape[2] || height >= base.shape[1]) {
          return { x: 0, y: 0, width: base.shape[2], height: base.shape[1] };
        }
        const grow = Math.max(1, 32 / width, 32 / height);
        width *= grow;
        height *= grow;
        // Keep the anchored point where it was on screen, then keep the box on
        // the sheet.
        const nx = Math.max(0, Math.min(px - width * ax, base.shape[2] - width));
        const ny = Math.max(0, Math.min(py - height * ay, base.shape[1] - height));
        return { x: nx, y: ny, width, height };
      });
    },
    [base],
  );

  /** Where the pointer is, as a 0..1 fraction of the plate. */
  const anchorFrom = useCallback((e: { clientX: number; clientY: number }) => {
    const c = canvasRef.current;
    if (!c) return undefined;
    const r = c.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return undefined;
    return [
      Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    ] as [number, number];
  }, []);

  /**
   * Resolution follows the zoom.
   *
   * Previously the level was chosen once at open and then held, so zooming in
   * just magnified blocky pixels from a 32x downsample and the image never got
   * sharper — the single worst thing about using this. Pick the FINEST level
   * whose read stays inside the budget every time the box changes.
   *
   * Level 0 on a small window is cheap (a chunk is [depth,128,128] and a tight
   * crop touches few of them); level 0 on the whole sheet is not, which is what
   * the budget is protecting against.
   */
  const [autoLevel, setAutoLevel] = useState(true);
  useEffect(() => {
    if (!autoLevel || !volume || !box) return;
    // Finest level within budget; if nothing fits (a whole-sheet view always
    // costs more than the budget, because a chunk is the entire depth stack)
    // fall through to the coarsest and let the read run.
    let best = volume.levels.length - 1;
    for (let i = 0; i < volume.levels.length; i++) {
      if (readCost(volume.levels[i], box).bytes <= OPEN_BUDGET_BYTES) {
        best = i;
        break;
      }
    }
    setLevelIndex((cur) => (cur === best ? cur : best));
  }, [box, volume, autoLevel]);

  const drag = useRef<{ x: number; y: number; box: ViewBox } | null>(null);
  const [offset, setOffset] = useState<{ dx: number; dy: number } | null>(null);
  const profileDrag = useRef<{ x: number; y: number } | null>(null);
  const painting = useRef(false);

  const labelling = labelFrame !== null;

  /** The mask for the layer currently on screen, created on first stroke. */
  const maskFor = useCallback(
    (layer: number): Uint8Array | null => {
      if (!labelFrame) return null;
      let m = masksRef.current.get(layer);
      if (!m) {
        m = new Uint8Array(labelFrame.width * labelFrame.height);
        masksRef.current.set(layer, m);
      }
      return m;
    },
    [labelFrame],
  );

  const paintAt = useCallback(
    (px: number, py: number) => {
      const mask = maskFor(zIndex);
      if (!mask || !labelFrame) return;
      const { width, height } = labelFrame;
      const r = brush;
      const value = erasing ? 0 : 255;
      for (let dy = -r; dy <= r; dy++) {
        for (let dx = -r; dx <= r; dx++) {
          if (dx * dx + dy * dy > r * r) continue;
          const x = px + dx;
          const y = py + dy;
          if (x < 0 || y < 0 || x >= width || y >= height) continue;
          mask[y * width + x] = value;
        }
      }
      setMaskVersion((v) => v + 1);
    },
    [maskFor, zIndex, labelFrame, brush, erasing],
  );

  // Draw the mask over the plate. Ochre at partial alpha, so the papyrus stays
  // visible underneath — you have to be able to see what you are labelling.
  useEffect(() => {
    const canvas = overlayRef.current;
    if (!canvas || !labelFrame) return;
    const { width, height } = labelFrame;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    const mask = masksRef.current.get(zIndex);
    if (!mask) return;
    const img = ctx.createImageData(width, height);
    for (let i = 0; i < width * height; i++) {
      if (!mask[i]) continue;
      const o = i * 4;
      img.data[o] = 0xc8;
      img.data[o + 1] = 0x97;
      img.data[o + 2] = 0x1f;
      img.data[o + 3] = 170;
    }
    ctx.putImageData(img, 0, 0);
  }, [maskVersion, zIndex, labelFrame]);

  const startLabelling = () => {
    if (!region || !box) return;
    masksRef.current = new Map();
    setMaskVersion(0);
    setProfileMode(false);
    setLabelFrame({
      levelIndex,
      box: { ...box },
      width: region.width,
      height: region.height,
    });
  };

  const stopLabelling = () => {
    setLabelFrame(null);
    masksRef.current = new Map();
    setMaskVersion(0);
  };

  /**
   * Exports one TIFF per painted layer plus a manifest.
   *
   * The manifest is the part that makes these usable by anyone else: a mask
   * with no provenance cannot be placed back into the volume it came from. It
   * records the specimen, the exact URL, level, layer index, crop origin in
   * that level's voxel coordinates, and the voxel size — everything needed to
   * put the label back where it was drawn.
   */
  const exportLabels = () => {
    if (!labelFrame || !level) return;
    const painted = [...masksRef.current.entries()]
      .filter(([, m]) => m.some((v) => v !== 0))
      .sort((a, b) => a[0] - b[0]);

    if (painted.length === 0) {
      setReadError("Nothing painted yet — no labels to export.");
      return;
    }

    const stem = `${specimen.id}-L${level.path}`;
    for (const [layer, mask] of painted) {
      downloadBlob(
        encodeGrayTiff(mask, labelFrame.width, labelFrame.height),
        `${stem}-layer${String(layer).padStart(3, "0")}-ink.tif`,
        "image/tiff",
      );
    }

    const manifest = {
      tool: "Slice — browser ink labeller",
      created: new Date().toISOString(),
      specimen: { id: specimen.id, label: specimen.label, url: specimen.url },
      source: source === "sheet" ? "surface-volume" : "scroll-volume",
      level: { path: level.path, inPlaneFactor: level.factor, depthFactor: level.zFactor },
      crop: {
        // Origin in this level's voxel coordinates, matching the TIFF's (0,0).
        x0: Math.round(labelFrame.box.x / level.factor),
        y0: Math.round(labelFrame.box.y / level.factor),
        width: labelFrame.width,
        height: labelFrame.height,
      },
      voxelUm: specimen.voxelUm,
      layers: painted.map(([layer, mask]) => ({
        layer,
        file: `${stem}-layer${String(layer).padStart(3, "0")}-ink.tif`,
        paintedVoxels: mask.reduce((n, v) => n + (v ? 1 : 0), 0),
      })),
      encoding: "uint8, 255 = ink, 0 = not labelled",
      note: "Labels are painted in a frame locked at creation time; the crop and level above are the frame they belong to.",
    };
    downloadBlob(JSON.stringify(manifest, null, 2), `${stem}-labels.json`, "application/json");
  };

  /** Pointer position → voxel coordinates in this level, plus the raw value. */
  const probe = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !region) return null;
    const r = canvas.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return null;
    const px = Math.floor(((e.clientX - r.left) / r.width) * region.width);
    const py = Math.floor(((e.clientY - r.top) / r.height) * region.height);
    if (px < 0 || py < 0 || px >= region.width || py >= region.height) return null;
    return { px, py, value: Number(region.data[py * region.width + px]) };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!box) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    if (labelling) {
      const p = probe(e);
      if (p) {
        painting.current = true;
        paintAt(p.px, p.py);
      }
      return;
    }
    if (profileMode) {
      const p = probe(e);
      if (p) profileDrag.current = { x: p.px, y: p.py };
      return;
    }
    drag.current = { x: e.clientX, y: e.clientY, box };
    setOffset({ dx: 0, dy: 0 });
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const p = probe(e);
    if (p && level && region) {
      setCursor({
        vx: Math.round((region.x0 + p.px) * level.factor),
        vy: Math.round((region.y0 + p.py) * level.factor),
        value: p.value,
      });
    } else {
      setCursor(null);
    }

    if (painting.current && p) {
      paintAt(p.px, p.py);
      return;
    }
    if (profileDrag.current && p && region) {
      setProfile(lineProfile(region, profileDrag.current, { x: p.px, y: p.py }));
      return;
    }
    if (!drag.current) return;
    setOffset({ dx: e.clientX - drag.current.x, dy: e.clientY - drag.current.y });
  };

  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    painting.current = false;
    profileDrag.current = null;
    const start = drag.current;
    const canvas = canvasRef.current;
    drag.current = null;
    setOffset(null);
    if (!start || !canvas || canvas.clientWidth === 0) return;
    const scale = start.box.width / canvas.clientWidth;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    if (dx === 0 && dy === 0) return;
    setBox({ ...start.box, x: start.box.x - dx * scale, y: start.box.y - dy * scale });
  };

  // Zoom is disabled while a label frame is open — see `labelFrame`.
  /**
   * Wheel zooms AT THE CURSOR, not at the centre of the view.
   *
   * Centre-anchored zoom is why this felt uncontrollable: you point at a word,
   * scroll, and the word leaves the screen. Anchoring to the pointer is the
   * one behaviour every map has, and it costs four lines.
   */
  const onWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    if (labelling) return;
    zoom(e.deltaY > 0 ? 1.25 : 0.8, anchorFrom(e));
  };

  /** Double-click zooms in on what you clicked. */
  const onDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (labelling || profileMode) return;
    zoom(0.5, anchorFrom(e));
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setReadError("Could not write to the clipboard. Copy the address bar instead.");
    }
  };

  const savePng = async () => {
    const canvas = canvasRef.current;
    if (!canvas || !box || !level) return;
    try {
      await exportPng(canvas, {
        scroll: specimen.label,
        level: level.path,
        z: zIndex,
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        window: window_,
        colormap: getColormap(colormap).label,
        voxelUm: specimen.voxelUm,
        url: window.location.href,
      });
    } catch (err) {
      setReadError(err instanceof Error ? err.message : String(err));
    }
  };

  const aspect = box && box.height > 0 ? box.width / box.height : 1;

  return (
    <div className="mx-auto max-w-[1240px] px-6 py-7">
      {/* Masthead */}
      <header className="mb-6 flex items-end justify-between gap-6 border-b border-rule pb-4">
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight text-papyrus">
            Slice
          </h1>
          <p className="caption mt-1 text-[13px]">
            Herculaneum micro-CT, streamed from the open bucket. Nothing downloaded.
          </p>
        </div>
        <div className="flex items-end gap-6">
          <a href="/record" className="btn whitespace-nowrap">
            The Record
          </a>
          <div className="hidden text-right sm:block">
            <p className="eyebrow">Specimen</p>
            <p className="font-display text-xl text-papyrus">{specimen.label}</p>
          </div>
        </div>
      </header>

      <div className="grid gap-7 lg:grid-cols-[1fr_286px]">
        <section>
          {/* Source — visible buttons, never a hidden menu. */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px] uppercase tracking-wider text-ash">
              Sheets · flattened
            </span>
            <span className="ml-auto text-[11px] text-ash">
              letters live here · ↑↓ depth · ←→ pan · drag to move · +/− zoom · 0 fit
            </span>
          </div>

          <div
            className="plate relative"
            style={{ aspectRatio: String(aspect) }}
          >
            {/* A surface chunk carries the whole depth stack of a tile, so a
                zoom-out can be a multi-second read. Without a visible sign of
                that, the old image just sits there and the button reads as
                dead — which is exactly how Fit and Out were reported broken
                when they were in fact working. */}
            {reading && (
              <div className="pointer-events-none absolute left-2 top-2 z-10 border border-ochre bg-void/85 px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ochre">
                reading{cost.chunks ? ` · ${cost.chunks} chunks` : ""}
                {cost.bytes
                  ? ` · ${(cost.bytes / 1e6).toFixed(0)} MB`
                  : ""}
              </div>
            )}
            {/*
              Letterbox, never stretch. `h-full w-full` forced every read into
              the plate's aspect regardless of the box's, so a wide sheet was
              squashed vertically and the papyrus weave sheared. A canvas is a
              replaced element with an intrinsic size, so max-* with auto
              width/height scales it down to fit and keeps the ratio — which is
              what lets Fit mean the whole sheet without deforming it.
            */}
            <canvas
              ref={canvasRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              onPointerLeave={() => setCursor(null)}
              onWheel={onWheel}
              onDoubleClick={onDoubleClick}
              className="m-auto block max-h-full max-w-full touch-none select-none"
              style={{
                imageRendering: "pixelated",
                cursor: labelling
                  ? "crosshair"
                  : profileMode
                    ? "crosshair"
                    : offset
                      ? "grabbing"
                      : "grab",
                transform: offset ? `translate(${offset.dx}px, ${offset.dy}px)` : undefined,
              }}
            />

            {labelling && (
              <canvas
                ref={overlayRef}
                className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
                style={{ imageRendering: "pixelated" }}
              />
            )}

            {/*
              Navigation belongs ON the map.
              Zoom lived in a right-hand sidebar next to a dozen scientific
              readouts, so moving around the papyrus meant leaving the papyrus.
              These are the same actions as the sidebar buttons, put where a
              hand already is. The sidebar copies stay for keyboard//precision
              use; this is the one you reach for.
            */}
            {status === "ready" && base && (
              <div className="absolute bottom-3 right-3 z-10 flex flex-col overflow-hidden border border-rule bg-void/85">
                <button
                  className="px-2.5 py-1.5 font-mono text-sm text-papyrus hover:bg-panel"
                  onClick={() => zoom(0.5)}
                  title="Zoom in — or scroll / double-click on the plate"
                  aria-label="Zoom in"
                >
                  +
                </button>
                <button
                  className="border-t border-rule px-2.5 py-1.5 font-mono text-sm text-papyrus hover:bg-panel"
                  onClick={() => zoom(2)}
                  title="Zoom out — or scroll down on the plate"
                  aria-label="Zoom out"
                >
                  −
                </button>
                <button
                  className="border-t border-rule px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ash hover:bg-panel hover:text-papyrus"
                  onClick={() =>
                    setBox({ x: 0, y: 0, width: base.shape[2], height: base.shape[1] })
                  }
                  title="Whole sheet — a large read, it will take a moment"
                  aria-label="Fit whole sheet"
                >
                  fit
                </button>
              </div>
            )}

            {/* Bottom-CENTRE: the scale bar owns bottom-left and the zoom
                controls own bottom-right, and this sat on top of the scale
                bar when it was put in the corner. */}
            {status === "ready" && (
              <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap font-mono text-[10px] uppercase tracking-wider text-ash/70">
                drag to move · scroll to zoom · double-click to zoom in
              </div>
            )}

            {/* How big a letter actually is, at this zoom. Without a reference
                the eye invents one, and papyrus damage makes handsome curves at
                ten times letter size. */}
            {letterScale && status === "ready" && source === "sheet" && (
              <div className="pointer-events-none absolute right-3 top-3 z-[3] text-right">
                {letterScale.tooSmallToSee ? (
                  <p className="font-mono text-[10px] text-ochre">
                    a letter is &lt; 1px here — zoom in
                  </p>
                ) : (
                  <>
                    <div
                      className="ml-auto border border-ochre/80 bg-ochre/10"
                      style={{
                        width: `${Math.min(letterScale.w * 100, 60)}%`,
                        paddingBottom: `${Math.min(letterScale.h * 100, 60)}%`,
                        minWidth: 2,
                      }}
                    />
                    <p className="mt-1 font-mono text-[10px] text-ochre">one letter</p>
                  </>
                )}
              </div>
            )}

            {/* Scale bar, drawn over the plate. */}
            {bar && status === "ready" && (
              <div className="pointer-events-none absolute bottom-3 left-3 z-[3]">
                <div
                  className="h-[3px] border-x-2 border-papyrus bg-papyrus"
                  style={{ width: `${Math.min(bar.fraction * 100, 60)}%`, minWidth: 40 }}
                />
                <p className="mt-1 font-mono text-[10px] text-papyrus drop-shadow">{bar.label}</p>
              </div>
            )}

            {status !== "ready" && (
              <div className="absolute inset-0 z-[3] grid place-items-center bg-void/85 p-6 text-center">
                <p className="font-mono text-xs text-ash">
                  {status === "opening" && "Reading volume metadata…"}
                  {status === "idle" && "Choose a specimen."}
                  {status === "error" && (
                    <span className="text-papyrus">
                      Could not open this volume.
                      <br />
                      <span className="mt-2 block text-ash">{error}</span>
                    </span>
                  )}
                </p>
              </div>
            )}
          </div>

          {/* Plate caption — the engraved line under an atlas figure. */}
          <p className="caption mt-2.5 text-[13px]">
            {specimen.label} · level {level?.path ?? "—"} · {depthLabel} {zIndex}
            {cursor && (
              <span className="not-italic font-mono text-[11px] text-ash">
                {" "}
                — voxel {cursor.vx}, {cursor.vy} reads {cursor.value}
              </span>
            )}
          </p>

          {/* Telemetry, as ledger figures. */}
          <div className="mt-5 grid grid-cols-2 gap-x-8 sm:grid-cols-4">
            <Figure label="chunks" value={String(stats.requests)} sub={`${stats.absent} empty`} />
            <Figure label="transferred" value={formatBytes(stats.bytes)} sub={`${Math.round(stats.networkMs)} ms`} />
            <Figure label="from cache" value={String(stats.hits)} sub={formatBytes(stats.hitBytes)} />
            <Figure
              label="this read"
              value={region ? `${Math.round(region.decodeMs)}` : "—"}
              sub="ms"
              live={reading}
            />
          </div>

          {/* Is this scan inside the bar this project sets for itself? The
              letter is never the problem — 347 voxels tall even on the coarsest
              scroll. The ink LAYER is ~15 um, which at 8.64 um is 1.7 voxels,
              under the ~3 we require before trusting our own cross-scan work.
              CORRECTED 2026-08-02 (villa PR #1295): this used to read as though
              a coarse scan meant the ink "was never recorded". It does not —
              PHerc0172 sits at 1.9 voxels and its title has been read. Say what
              WE will assert, not what the data supposedly cannot hold. */}
          {res.verdict !== "resolved" && status === "ready" && (
            <p className="mt-3 border border-ochre/40 bg-ochre/5 px-3 py-2 font-mono text-[11px] text-ochre">
              Ink layer is ~{HAND.inkLayerUm} µm — {res.inkVoxels.toFixed(1)} voxels at
              this scan&apos;s {specimen.voxelUm} µm sampling, below the ~3 needed to
              resolve a feature. A letter here is {Math.round(res.letterVoxels).toLocaleString()} voxels,
              so size is not the limit — the ink layer is under-sampled at this
              scan. Scroll 1 gets 6.2 voxels through the same layer. This is a bar on
              what this tool will claim, not a verdict on the scroll: ink has been
              published on scrolls below it.
            </p>
          )}

          {/* Is this text, or is it fibre? Papyrus is periodic at roughly a
              sixth of a line pitch, so the period tells them apart where
              brightness cannot. Thresholded noise looks like letters to
              everyone; this is the cheapest available defence against it. */}
          {source === "sheet" && textCheck && status === "ready" && (
            <div className="mt-3 border border-rule bg-panel px-3 py-2 font-mono text-[11px]">
              {textCheck.tooShort ? (
                <span className="text-ash">
                  <span className="text-papyrus">Text check:</span> view is too short to
                  judge — needs about {textCheck.needMm.toFixed(0)} mm of height to see
                  line spacing. Zoom out.
                </span>
              ) : (
                <span className={textCheck.verdict === "consistent" ? "text-ochre" : "text-ash"}>
                  <span className="text-papyrus">Text check:</span> strongest spacing{" "}
                  {(textCheck.pitchUm / 1000).toFixed(2)} mm (r={textCheck.strength.toFixed(2)}).{" "}
                  {textCheck.verdict === "consistent" &&
                    `Consistent with lines of text (~${(HAND.linePitchUm / 1000).toFixed(2)} mm). Not proof — only "not obviously fibre".`}
                  {textCheck.verdict === "wrong-period" &&
                    `Text sits near ${(HAND.linePitchUm / 1000).toFixed(2)} mm; this period is fibre or damage, not writing.`}
                  {textCheck.verdict === "too-weak" &&
                    `Too weak to call either way — no periodic structure worth trusting here, at any spacing.`}
                </span>
              )}
            </div>
          )}

          {readError && (
            <p className="mt-3 border border-rule bg-panel px-3 py-2 font-mono text-[11px] text-papyrus">
              Read failed. {readError}
            </p>
          )}

          {cost.bytes > COST_WARN_BYTES && (
            <p className="mt-3 border border-ochre/40 bg-ochre/5 px-3 py-2 font-mono text-[11px] text-ochre">
              Up to {cost.chunks} chunks — {formatBytes(cost.bytes)} at worst, because a slice
              pulls the full chunk depth. Empty chunks outside the mask are free, so the real
              cost is usually lower.
            </p>
          )}

          {/* Line profile — the ink-hunting instrument. */}
          {profile && (
            <div className="mt-5">
              <p className="eyebrow mb-1.5">Density along the line</p>
              <Sparkline values={profile} height={72} />
              <p className="caption mt-1 text-[12px]">
                Sheets read as a regular train of peaks. Where the train breaks, stalls or
                doubles, something is happening.
              </p>
            </div>
          )}
        </section>

        <aside className="text-xs">
          <p className="eyebrow mb-2">Specimen</p>
          <select
            value={specimenId}
            onChange={(e) => setSpecimenId(e.target.value)}
            className="mb-2 w-full border border-rule bg-panel px-2 py-1.5 font-mono text-papyrus"
          >
            {catalog.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <p className="caption mb-5 text-[12px] leading-snug">{specimen.note}</p>

          {volume && level && base && box && (
            <>
              <div className="ledger mb-5">
                <Row label="dimensions">
                  {level.shape[2]} × {level.shape[1]} × {level.shape[0]}
                </Row>
                <Row label="downsample">{level.factor}×</Row>
                <Row label="voxel">{specimen.voxelUm} µm</Row>
                <Row label="ink layer">
                  <span
                    className={
                      res.verdict === "resolved"
                        ? "text-papyrus"
                        : res.verdict === "marginal"
                          ? "text-ochre"
                          : "text-ochre"
                    }
                  >
                    {res.inkVoxels.toFixed(1)} vox
                    {res.verdict !== "resolved" && " ⚠"}
                  </span>
                </Row>
                <Row label="field">
                  {(box.width * specimen.voxelUm) / 1000 > 1
                    ? `${((box.width * specimen.voxelUm) / 1000).toFixed(1)} mm`
                    : `${Math.round(box.width * specimen.voxelUm)} µm`}
                </Row>
                <Row label="read at most">
                  {cost.chunks} · {formatBytes(cost.bytes)}
                </Row>
              </div>

              <Field label={`Level ${level.path}`}>
                <input
                  type="range"
                  min={0}
                  max={volume.levels.length - 1}
                  value={levelIndex}
                  onChange={(e) => {
                    setAutoLevel(false);
                    setLevelIndex(Number(e.target.value));
                  }}
                />
              </Field>

              <Field label={`${depthLabel} ${z} · index ${zIndex} of ${level.shape[0]}`}>
                {/* The measured ink band, drawn on the rail itself. Reading a
                    blindly-centred band scores AUC 0.654; this band scores
                    0.944. The single most expensive lesson of the campaign,
                    made unmissable where the mistake happens. */}
                <div className="relative">
                  {source === "sheet" && base.shape[0] > INK_BAND.hi ? (
                    <span
                      aria-hidden
                      className="pointer-events-none absolute top-1/2 h-[5px] -translate-y-1/2 bg-ochre/35"
                      style={{
                        left: `${(100 * INK_BAND.lo) / (base.shape[0] - 1)}%`,
                        width: `${(100 * (INK_BAND.hi - INK_BAND.lo)) / (base.shape[0] - 1)}%`,
                      }}
                    />
                  ) : null}
                  <input
                    type="range"
                    className="relative"
                    min={0}
                    max={base.shape[0] - 1}
                    value={z}
                    onChange={(e) => setZ(Number(e.target.value))}
                  />
                </div>
                {source === "sheet" && base.shape[0] > INK_BAND.hi ? (
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <p className="text-[10px] text-ash">↑ ↓ to step · shift for ten</p>
                    <button
                      className="btn px-2 py-0.5 text-[10px]"
                      onClick={() => setZ(Math.round((INK_BAND.lo + INK_BAND.hi) / 2))}
                      title="Layers 27–89, measured: AUC 0.654 blind-centred vs 0.944 in-band"
                    >
                      Ink band {INK_BAND.lo}–{INK_BAND.hi}
                    </button>
                  </div>
                ) : (
                  <p className="mt-1 text-[10px] text-ash">↑ ↓ to step · shift for ten</p>
                )}
              </Field>

              <Field label="View">
                <div className="flex gap-1.5">
                  <button className="btn flex-1" onClick={() => zoom(0.5)}>
                    In
                  </button>
                  <button className="btn flex-1" onClick={() => zoom(2)}>
                    Out
                  </button>
                  <button
                    className="btn flex-1"
                    onClick={() =>
                      // Fit means the WHOLE sheet. A surface chunk carries the
                      // full depth stack of a tile, so this is an expensive
                      // read (~900 chunks, tens of seconds on a big segment) --
                      // but expensive is not broken, and clamping it to a
                      // budget turned a slow button into a dead one.
                      setBox({ x: 0, y: 0, width: base.shape[2], height: base.shape[1] })
                    }
                  >
                    Fit
                  </button>
                </div>
              </Field>

              {!labelSeg && !inkSheet && !hasCrossScan && (
                <Field label="Ink overlay">
                  <p className="caption text-[11px]">
                    No published ink detection for this sheet. There are 367
                    sheets across 7 scrolls that have one.
                  </p>
                  <button
                    className="btn mt-2 w-full"
                    onClick={() => setSpecimenId(DEFAULT_SPECIMEN)}
                  >
                    Go to a sheet with ink
                  </button>
                </Field>
              )}

              {labelSeg && (
                <Field label="Ink overlay">
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      className="btn"
                      data-active={showLabels}
                      onClick={() => setShowLabels((v) => !v)}
                    >
                      {showLabels ? "On" : "Off"}
                    </button>
                    <a className="btn text-center" href="/qc">
                      Map ↗
                    </a>
                  </div>

                  {/* Whose overlay. Visible buttons, not a dropdown — this is a
                      primary choice, and the two are not the same claim. */}
                  {inkSheet && hasCrossScan && (
                    <div className="mt-2 grid grid-cols-2 gap-1.5">
                      <button
                        className="btn"
                        data-active={labelKind === "published"}
                        onClick={() => setLabelKind("published")}
                      >
                        Theirs
                      </button>
                      <button
                        className="btn"
                        data-active={labelKind === "cross-scan"}
                        onClick={() => setLabelKind("cross-scan")}
                      >
                        Ours
                      </button>
                    </div>
                  )}

                  {/* Two checkpoints on one volume: PHerc0172's 53 sheets. */}
                  {labelKind === "published" && inkSheet &&
                    inkSheet.maps.length > 1 && (
                      <div className="mt-2 grid gap-1.5">
                        {inkSheet.maps.map((m, i) => (
                          <button
                            key={m.url}
                            className="btn truncate text-left"
                            data-active={i === mapIndex}
                            onClick={() => setMapIndex(i)}
                            title={m.model}
                          >
                            {m.model.replace(/^\d+-/, "")}
                          </button>
                        ))}
                      </div>
                    )}

                  <input
                    type="range"
                    min={0.15}
                    max={1}
                    step={0.05}
                    value={labelAlpha}
                    onChange={(e) => setLabelAlpha(Number(e.target.value))}
                    className="mt-2 w-full accent-ochre"
                    disabled={!showLabels}
                  />

                  {labelKind === "published" && inkThreshold !== null &&
                    inkDefault !== null && (
                      <>
                        <div className="ledger-row mt-2">
                          <span>SCORE CUTOFF</span>
                          <span className="tabular-nums">
                            {inkThreshold}
                            {inkThreshold < inkDefault && (
                              <span className="text-ochre">
                                {" "}
                                −{inkDefault - inkThreshold}
                              </span>
                            )}
                          </span>
                        </div>
                        <input
                          type="range"
                          min={1}
                          max={255}
                          step={1}
                          value={inkThreshold}
                          onChange={(e) =>
                            setInkThreshold(Number(e.target.value))
                          }
                          className="mt-1 w-full accent-ochre"
                          disabled={!showLabels}
                        />
                        <p className="caption mt-1 text-[11px] text-ash">
                          Default {inkDefault} is the top decile of this
                          sheet&apos;s own scores — the cutoff the Scroll 1
                          control passed at. Lower it and{" "}
                          <span style={{ color: "#c8971f" }}>■</span> marks what
                          you added, so a relaxed threshold cannot quietly grow
                          the white. Below the default is model output nobody
                          publishes; it is also where you will fool yourself.
                        </p>
                      </>
                    )}

                  <p className="caption mt-2 text-[11px]">
                    {labelKind === "published" ? (
                      <>
                        <strong className="text-ochre">
                          NOT OUR DETECTION.
                        </strong>{" "}
                        <span style={{ color: "#e9e5db" }}>■</span> is Vesuvius
                        Challenge&apos;s own published ink map, read live from
                        their public bucket and drawn on the papyrus. We did not
                        detect this ink, did not read it, and contributed
                        nothing to it. This viewer shows it; it does not claim
                        it.
                      </>
                    ) : (
                      <>
                        <span style={{ color: "#e9e5db" }}>■</span> both scans
                        call ink · <span style={{ color: "#c8971f" }}>■</span>{" "}
                        only one. Blank and unlabelled are transparent. This one
                        is ours — a cross-scan comparison of their two published
                        maps, not a detection of our own.
                      </>
                    )}
                  </p>

                  {labelKind === "published" && inkSheet && (
                    <p className="caption mt-1 text-[11px] text-ash">
                      Model{" "}
                      <span className="text-papyrus">
                        {inkSheet.maps[mapIndex]?.model}
                      </span>
                      . Scroll data CC BY-NC 4.0, © Vesuvius Challenge.
                    </p>
                  )}

                  <p className="caption mt-1 text-[11px] text-ash">
                    The map is drawn on this sheet&apos;s own canvas — the grid
                    it was computed on — so placement is a pure scale, measured
                    per sheet rather than assumed. It is 8× coarser than the
                    slice, so its edges are blocky by construction, not by
                    misregistration. Treat the overlay as regional, not exact.
                  </p>
                </Field>
              )}

              <Field label="Colour ramp">
                <div className="grid grid-cols-2 gap-1.5">
                  {COLORMAPS.map((c) => (
                    <button
                      key={c.id}
                      className="btn"
                      data-active={colormap === c.id}
                      onClick={() => setColormap(c.id)}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
                <p className="caption mt-1.5 text-[12px] leading-snug">
                  {getColormap(colormap).note}
                </p>
              </Field>

              <Field label={`Window ${window_[0]}–${window_[1]}`}>
                {hist && <Histogram bins={hist.bins} peak={hist.peak} lo={window_[0]} hi={window_[1]} />}
                <label className="mt-1.5 flex items-center gap-2 text-ash">
                  <input
                    type="checkbox"
                    checked={autoLevels}
                    onChange={(e) => setAutoLevels(e.target.checked)}
                    className="accent-ochre"
                  />
                  Set automatically
                </label>
                {!autoLevels && (
                  <div className="mt-2 space-y-2">
                    <input
                      type="range"
                      min={0}
                      max={255}
                      value={window_[0]}
                      onChange={(e) => setWindow(([, hi]) => [Number(e.target.value), hi])}
                    />
                    <input
                      type="range"
                      min={0}
                      max={255}
                      value={window_[1]}
                      onChange={(e) => setWindow(([lo]) => [lo, Number(e.target.value)])}
                    />
                  </div>
                )}
              </Field>

              <Field label="Ink labels">
                {!labelling ? (
                  <>
                    <button className="btn w-full" onClick={startLabelling} disabled={!region}>
                      Label this frame
                    </button>
                    <p className="caption mt-1.5 text-[12px] leading-snug">
                      Locks the crop and level, then paint ink layer by layer. Depth is
                      the point: scrub until the ink resolves, label it there.
                    </p>
                  </>
                ) : (
                  <>
                    <div className="flex gap-1.5">
                      <button
                        className="btn flex-1"
                        data-active={!erasing}
                        onClick={() => setErasing(false)}
                      >
                        Ink
                      </button>
                      <button
                        className="btn flex-1"
                        data-active={erasing}
                        onClick={() => setErasing(true)}
                      >
                        Erase
                      </button>
                    </div>
                    <p className="ledger-label mt-2.5">brush {brush} px</p>
                    <input
                      type="range"
                      min={1}
                      max={20}
                      value={brush}
                      onChange={(e) => setBrush(Number(e.target.value))}
                    />
                    <div className="ledger mt-2.5">
                      <Row label="layers painted">{paintedLayerCount}</Row>
                      <Row label="frame">
                        {labelFrame.width} × {labelFrame.height}
                      </Row>
                    </div>
                    <button className="btn mt-2 w-full" onClick={exportLabels}>
                      Export TIFF + manifest
                    </button>
                    <button className="btn mt-1.5 w-full" onClick={stopLabelling}>
                      Discard frame
                    </button>
                    <p className="caption mt-1.5 text-[12px] leading-snug">
                      Pan and zoom are locked so strokes cannot drift off the surface
                      they describe. Depth still moves.
                    </p>
                  </>
                )}
              </Field>

              <Field label="Instruments">
                <button
                  className="btn w-full"
                  data-active={profileMode}
                  disabled={labelling}
                  onClick={() => {
                    setProfileMode((v) => !v);
                    if (profileMode) setProfile(null);
                  }}
                >
                  {profileMode ? "Profile: drag a line" : "Density profile"}
                </button>
                <button className="btn mt-1.5 w-full" onClick={savePng}>
                  Export PNG
                </button>
                <button className="btn mt-1.5 w-full" onClick={copyLink}>
                  {copied ? "Copied" : "Copy link"}
                </button>
              </Field>
            </>
          )}
        </aside>
      </div>

      {/* Attribution. The data is the substance of this thing and it is
          published under terms; crediting it in a file nobody opens is not
          crediting it. */}
      <footer className="mt-10 border-t border-rule pt-4">
        <p className="caption text-[12px] leading-relaxed">
          Scan data: Angelotti, Parsons, Johnson, Dal Prà, Rudolph, Tafforeau, Mirone,
          Henderson, Schilling, McDonald, Josey, Nader, Parker &amp; Seales,{" "}
          <em>Vesuvius Challenge — CT Scans of Herculaneum Papyri</em>. Scroll 1 is from
          the{" "}
          <a
            className="underline decoration-rule underline-offset-2 hover:text-ochre"
            href="https://doi.org/10.48550/arXiv.2304.02084"
            target="_blank"
            rel="noopener noreferrer"
          >
            EduceLab-Scrolls
          </a>{" "}
          dataset (Parsons et al., 2023), © EduceLab / University of Kentucky.
        </p>
        <p className="mt-1.5 font-mono text-[10px] uppercase tracking-wider text-ash">
          Data CC BY-NC 4.0 · code MIT · this viewer re-hosts nothing — your browser
          reads the public bucket directly
        </p>
      </footer>
    </div>
  );
}

/* ---- small pieces ------------------------------------------------------ */

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="ledger-row">
      <span className="ledger-label">{label}</span>
      <span className="ledger-value font-mono text-[11px]">{children}</span>
    </div>
  );
}

function Figure({
  label,
  value,
  sub,
  live,
}: {
  label: string;
  value: string;
  sub?: string;
  live?: boolean;
}) {
  return (
    <div className="border-t border-rule pt-2">
      <p className="ledger-label">{label}</p>
      <p className={`ledger-figure mt-1 ${live ? "text-ochre" : "text-papyrus"}`}>{value}</p>
      {sub && <p className="mt-0.5 font-mono text-[10px] text-ash">{sub}</p>}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <p className="eyebrow mb-1.5">{label}</p>
      {children}
    </div>
  );
}

/** Histogram of the visible crop with the display window drawn over it. */
function Histogram({
  bins,
  peak,
  lo,
  hi,
}: {
  bins: number[];
  peak: number;
  lo: number;
  hi: number;
}) {
  const pts = bins
    .map((b, i) => `${(i / 255) * 100},${40 - (b / peak) * 40}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-11 w-full">
      <rect
        x={(lo / 255) * 100}
        y={0}
        width={((hi - lo) / 255) * 100}
        height={40}
        fill="var(--color-ochre)"
        opacity={0.14}
      />
      <polyline points={pts} fill="none" stroke="var(--color-ash)" strokeWidth={0.7} />
    </svg>
  );
}

function Sparkline({ values, height }: { values: number[]; height: number }) {
  const max = Math.max(1, ...values);
  const pts = values
    .map((v, i) => `${(i / (values.length - 1 || 1)) * 100},${height - (v / max) * height}`)
    .join(" ");
  return (
    <svg
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      className="w-full border border-rule bg-panel"
      style={{ height }}
    >
      <polyline points={pts} fill="none" stroke="var(--color-ochre)" strokeWidth={0.8} />
    </svg>
  );
}

type SeedState = {
  source: Source | null;
  specimenId: string | null;
  level: number | null;
  z: number | null;
  box: ViewBox | null;
  colormap: ColormapId | null;
  applied: boolean;
};

function readUrlState(params: URLSearchParams): SeedState {
  const num = (key: string): number | null => {
    const raw = params.get(key);
    if (raw === null) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const src = params.get("src");
  const source: Source | null = src === "sheet" || src === "scroll" ? src : null;
  const v = params.get("v");
  const known = v ? Boolean(findVolume(v) ?? findSurface(v)) : false;
  const c = params.get("c");
  const x = num("x");
  const y = num("y");
  const w = num("w");
  const h = num("h");

  return {
    source,
    specimenId: known ? v : null,
    level: num("l"),
    z: num("z"),
    box: x !== null && y !== null && w !== null && h !== null && w > 0 && h > 0
      ? { x, y, width: w, height: h }
      : null,
    colormap: COLORMAPS.some((m) => m.id === c) ? (c as ColormapId) : null,
    applied: false,
  };
}

function clampInt(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(v)));
}
