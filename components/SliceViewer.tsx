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
   * Default to a LABELLED sheet, not a raw scroll.
   *
   * The old default was PHerc. 125 raw — a cross-section in which letters
   * cannot appear at all by geometry, and which carries no labels, so a first
   * visit showed a grey blob and none of the work. Land on a PHerc0139 sheet
   * that has cross-scan labels instead; the raw scrolls are one click away.
   */
  const DEFAULT_SOURCE: Source = "sheet";
  const DEFAULT_SPECIMEN = "0139-20260302000001";
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
   * Cross-scan label overlay.
   *
   * The published ink map is written on this surface volume's own canvas, so a
   * label pixel maps to the sheet by a pure scale and the overlay needs no
   * registration: source rect = view box / (8 * png downsample). Verified on
   * all 37 PHerc0139 segments to within ~2% of a letter.
   *
   * Only PHerc0139 sheets have labels; everything else leaves this off and the
   * control hidden, rather than showing an empty toggle.
   */
  const [showLabels, setShowLabels] = useState(true);
  const [labelAlpha, setLabelAlpha] = useState(0.55);
  /**
   * The recoloured overlay is cached. Rebuilding it inside the paint effect
   * meant recolouring up to 2M pixels on every pan, zoom, window and colormap
   * change, which made the overlay visibly lag in and out. It depends only on
   * the label raster, so it is built once per segment.
   */
  const labelCanvas = useRef<HTMLCanvasElement | null>(null);
  const labelDsRef = useRef<number | null>(null);
  /** Always changes when a raster is (un)loaded, so the paint effect re-runs
   *  even when two segments happen to share a downsample factor. */
  const [labelVersion, setLabelVersion] = useState(0);
  const [labelSeg, setLabelSeg] = useState<string | null>(null);
  const [labelKind, setLabelKind] =
    useState<"cross-scan" | "published" | null>(null);
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

  // Fetch the label raster for this sheet, if one exists, and recolour it once.
  useEffect(() => {
    labelCanvas.current = null;
    labelDsRef.current = null;
    setLabelSeg(null);
    setLabelKind(null);
    setLabelVersion((v) => v + 1);
    if (source !== "sheet") return;
    let cancelled = false;

    /**
     * Two kinds of overlay.
     *
     *   cross-scan  PHerc0139 only — 37 segments with maps at two energies,
     *               so the raster carries agree / disagree / silent.
     *   published   Scroll 1 — the best sheet in the library (3.00 mm hand,
     *               where letterforms actually resolve) but only ONE usable
     *               energy, so there is nothing to cross-check. This is the
     *               project's published detection on its own, and it is the
     *               positive control: if our overlay does not land on the
     *               letters that were read from this sheet in 2023, the
     *               machinery is wrong.
     */
    const load = (
      url: string,
      ds: number,
      seg: string,
      kind: "cross-scan" | "published",
    ) => {
      const img = new Image();
      img.onload = () => {
        if (cancelled) return;
        const off = document.createElement("canvas");
        off.width = img.width;
        off.height = img.height;
        const oc = off.getContext("2d", { willReadFrequently: true });
        if (!oc) return;
        oc.drawImage(img, 0, 0);
        const px = oc.getImageData(0, 0, img.width, img.height);
        for (let p = 0; p < px.data.length; p += 4) {
          const code = px.data[p];
          const disputed = px.data[p + 1] > 127;
          if (code === 1) {
            px.data[p] = 233; px.data[p + 1] = 229; px.data[p + 2] = 219;
            px.data[p + 3] = 255;
          } else if (code === 3 || disputed) {
            px.data[p] = 200; px.data[p + 1] = 151; px.data[p + 2] = 31;
            px.data[p + 3] = 255;
          } else {
            px.data[p + 3] = 0;
          }
        }
        oc.putImageData(px, 0, 0);
        labelCanvas.current = off;
        labelDsRef.current = ds;
        setLabelSeg(seg);
        setLabelKind(kind);
        setLabelVersion((v) => v + 1);
      };
      img.src = url;
    };

    if (specimenId === "Paris4-20231005123336-2.4um") {
      fetch("/qc/scroll1.json")
        .then((r) => r.json())
        .then((d: { downsample: number; segment: string }) => {
          if (cancelled) return;
          // scroll1.json stores the FULL factor (png px -> surface level 0),
          // while the 0139 index stores the ds8 factor, so divide by 8 here to
          // keep one convention downstream.
          load(`/qc/scroll1-${d.segment}.png`, d.downsample / 8, d.segment,
               "published");
        })
        .catch(() => undefined);
      return () => {
        cancelled = true;
      };
    }

    const seg = specimenId.startsWith("0139-")
      ? specimenId.slice("0139-".length)
      : null;
    if (!seg) return;
    fetch("/qc/index.json")
      .then((r) => r.json())
      .then((d: { segments: { segment: string; downsample: number }[] }) => {
        const entry = d.segments.find((x) => x.segment === seg);
        if (!entry || cancelled) return;
        load(`/qc/${seg}.png`, entry.downsample, seg, "cross-scan");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [specimenId, source]);

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
    const ds = labelDsRef.current;
    if (!showLabels || !lc || !ds || !box) return;
    const f = 8 * ds; // surface level-0 px per label px
    const sx = box.x / f;
    const sy = box.y / f;
    const sw = box.width / f;
    const sh = box.height / f;
    if (sw <= 0 || sh <= 0) return;
    ctx.save();
    ctx.globalAlpha = labelAlpha;
    ctx.imageSmoothingEnabled = false;
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
    (factor: number) => {
      setBox((current) => {
        if (!current || !base) return current;
        const cx = current.x + current.width / 2;
        const cy = current.y + current.height / 2;
        let width = Math.min(base.shape[2], Math.max(32, current.width * factor));
        let height = Math.min(base.shape[1], Math.max(32, current.height * factor));
        // Zooming out past what the coarsest level can serve produces a read
        // that never returns, which reads to a user as a dead button.
        if (factor > 1 && volumeRef.current) {
          const ls = volumeRef.current.levels;
          const cap = fitBudget(ls[ls.length - 1], OPEN_BUDGET_BYTES);
          width = Math.min(width, cap.width);
          height = Math.min(height, cap.height);
        }
        const nx = Math.max(0, Math.min(cx - width / 2, base.shape[2] - width));
        const ny = Math.max(0, Math.min(cy - height / 2, base.shape[1] - height));
        return { x: nx, y: ny, width, height };
      });
    },
    [base],
  );

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
  const onWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    if (labelling) return;
    zoom(e.deltaY > 0 ? 1.25 : 0.8);
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

          <div className="plate" style={{ aspectRatio: String(aspect) }}>
            <canvas
              ref={canvasRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              onPointerLeave={() => setCursor(null)}
              onWheel={onWheel}
              className="block h-full w-full touch-none select-none"
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

          {/* Can this scan hold ink at all? The letter is never the problem —
              347 voxels tall even on the coarsest scroll. The ink LAYER is
              ~15 um, and at 8.64 um sampling that is 1.7 voxels, under the ~3
              needed to resolve anything. Better to say so than to let someone
              spend a month hunting a signal the scan never recorded. */}
          {res.verdict !== "resolved" && status === "ready" && (
            <p className="mt-3 border border-ochre/40 bg-ochre/5 px-3 py-2 font-mono text-[11px] text-ochre">
              Ink layer is ~{HAND.inkLayerUm} µm — {res.inkVoxels.toFixed(1)} voxels at
              this scan&apos;s {specimen.voxelUm} µm sampling, below the ~3 needed to
              resolve a feature. A letter here is {Math.round(res.letterVoxels).toLocaleString()} voxels,
              so size is not the limit — the ink is under-sampled, not faint. Scroll 1
              gets 6.2 voxels through the same layer, which is why it could be read.
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
                    onClick={() => {
                      // A surface chunk is the WHOLE depth stack of a tile, so
                      // the full sheet is a ~385 MB read even at the coarsest
                      // level and the request simply hangs. Fit to the largest
                      // view the coarsest level can actually serve.
                      const coarse = volume.levels[volume.levels.length - 1];
                      setBox(fitBudget(coarse, OPEN_BUDGET_BYTES));
                    }}
                  >
                    Fit
                  </button>
                </div>
              </Field>

              {!labelSeg && (
                <Field label="Cross-scan labels">
                  <p className="caption text-[11px]">
                    No cross-scan labels for this sheet. They exist for the 37
                    PHerc0139 segments that were scanned at two energies.
                  </p>
                  <button
                    className="btn mt-2 w-full"
                    onClick={() => setSpecimenId(DEFAULT_SPECIMEN)}
                  >
                    Go to a labelled sheet
                  </button>
                </Field>
              )}

              {labelSeg && (
                <Field
                  label={
                    labelKind === "published"
                      ? "Published ink"
                      : "Cross-scan labels"
                  }
                >
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
                  <p className="caption mt-1 text-[11px]">
                    {labelKind === "published" ? (
                      <>
                        <span style={{ color: "#e9e5db" }}>■</span> the
                        project&apos;s published ink detection for this sheet.
                        Scroll 1 has one usable energy, so there is no second
                        scan to cross-check — this is their call, not ours, and
                        it is the positive control for the overlay.
                      </>
                    ) : (
                      <>
                        <span style={{ color: "#e9e5db" }}>■</span> both scans
                        call ink · <span style={{ color: "#c8971f" }}>■</span>{" "}
                        only one. Blank and unlabelled are transparent.
                      </>
                    )}
                  </p>
                  <p className="caption mt-1 text-[11px] text-ash">
                    Labels are 18 µm/px against this volume&apos;s 2.258, so the
                    overlay is 8× coarser than the slice and its edges are
                    blocky by construction, not by misregistration. It is drawn
                    on the sheet&apos;s own canvas — the grid the ink map was
                    computed on — so the mapping is a pure scale, verified on
                    all 37 segments to within ~2% of a letter. Pixel-level
                    agreement between white and visible ink has not been
                    spot-checked; treat the overlay as regional, not exact.
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
