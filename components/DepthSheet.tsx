"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  autoWindow,
  formatBytes,
  newStats,
  openVolume,
  readSlice,
  toImageData,
  type FetchStats,
  type Volume,
} from "@/lib/zarr";
import { SURFACES } from "@/lib/surfaces";
import { VOLUMES } from "@/lib/volumes";
import { COLORMAPS, getColormap, type ColormapId } from "@/lib/colormaps";

/**
 * Depth contact sheet.
 *
 * Ink sits at one depth inside the sheet, and finding that depth is most of the
 * work of reading. Scrubbing a slider one layer at a time is a slow way to
 * search a stack of a hundred; laying every layer out at once and looking is
 * fast.
 *
 * This is cheap for a reason specific to how the data is stored: a surface
 * volume chunk is [depth, 128, 128] — the *whole* depth stack of a tile in one
 * object. So the layers after the first cost no network at all. The one fetch
 * buys the entire sheet, and the readout below says exactly what it cost.
 */

type Target = { id: string; label: string; url: string; kind: "sheet" | "scroll" };

const TARGETS: Target[] = [
  ...SURFACES.map((s) => ({ id: s.id, label: s.label, url: s.url, kind: "sheet" as const })),
  ...VOLUMES.slice(0, 3).map((v) => ({
    id: v.id,
    label: `${v.label} (raw — no letters here)`,
    url: v.url,
    kind: "scroll" as const,
  })),
];

const TILE = 192;

export default function DepthSheet() {
  const [targetId, setTargetId] = useState(TARGETS[0].id);
  const [levelIndex, setLevelIndex] = useState(3);
  const [colormap, setColormap] = useState<ColormapId>("graphite");
  const [volume, setVolume] = useState<Volume | null>(null);
  const [status, setStatus] = useState<"idle" | "opening" | "reading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<{ index: number; image: ImageData }[]>([]);
  const [stats, setStats] = useState<FetchStats>(newStats);
  const [selected, setSelected] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);

  const statsRef = useRef<FetchStats>(newStats());
  const target = TARGETS.find((t) => t.id === targetId) ?? TARGETS[0];

  useEffect(() => {
    const controller = new AbortController();
    setStatus("opening");
    setError(null);
    setVolume(null);
    setLayers([]);
    setSelected(null);
    statsRef.current = newStats();
    setStats({ ...statsRef.current });

    openVolume(target.url, statsRef.current, controller.signal)
      .then((v) => {
        if (controller.signal.aborted) return;
        setVolume(v);
        setLevelIndex((i) => Math.min(i, v.levels.length - 1));
        setStatus("ready");
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setStatus("error");
        setError(e instanceof Error ? e.message : String(e));
      });

    return () => controller.abort();
  }, [target.url]);

  const run = useCallback(async () => {
    if (!volume) return;
    const level = volume.levels[Math.min(levelIndex, volume.levels.length - 1)];
    const depth = level.shape[0];
    setStatus("reading");
    setLayers([]);
    setProgress(0);

    // A tile from the middle of whatever is there.
    const w = Math.min(TILE, level.shape[2]);
    const h = Math.min(TILE, level.shape[1]);
    const x = Math.max(0, Math.floor(level.shape[2] / 2 - w / 2));
    const y = Math.max(0, Math.floor(level.shape[1] / 2 - h / 2));

    // Cap the sheet so a 2,000-slice raw volume does not try to draw itself.
    const step = Math.max(1, Math.ceil(depth / 60));
    const wanted: number[] = [];
    for (let i = 0; i < depth; i += step) wanted.push(i);

    const out: { index: number; image: ImageData }[] = [];
    try {
      for (const index of wanted) {
        const region = await readSlice(level, index, { x, y, width: w, height: h });
        const [lo, hi] = autoWindow(region.data);
        out.push({
          index,
          image: toImageData(region, lo, hi, getColormap(colormap).lut),
        });
        setProgress(out.length / wanted.length);
        setStats({ ...statsRef.current });
      }
      setLayers(out);
      setStatus("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, [volume, levelIndex, colormap]);

  return (
    <div>
      <div className="mb-5 grid gap-4 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
        <div>
          <p className="eyebrow mb-1.5">Specimen</p>
          <select
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            className="w-full border border-rule bg-panel px-2 py-1.5 font-mono text-xs text-papyrus"
          >
            {TARGETS.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <p className="eyebrow mb-1.5">Level</p>
          <select
            value={levelIndex}
            onChange={(e) => setLevelIndex(Number(e.target.value))}
            className="border border-rule bg-panel px-2 py-1.5 font-mono text-xs text-papyrus"
          >
            {(volume?.levels ?? []).map((l, i) => (
              <option key={l.path} value={i}>
                {l.path} · {l.factor}×
              </option>
            ))}
          </select>
        </div>

        <div>
          <p className="eyebrow mb-1.5">Ramp</p>
          <select
            value={colormap}
            onChange={(e) => setColormap(e.target.value as ColormapId)}
            className="border border-rule bg-panel px-2 py-1.5 font-mono text-xs text-papyrus"
          >
            {COLORMAPS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        <button className="btn" onClick={run} disabled={!volume || status === "reading"}>
          {status === "reading" ? `Reading ${Math.round(progress * 100)}%` : "Build sheet"}
        </button>
      </div>

      <div className="ledger mb-5">
        <Row label="chunks fetched">
          {stats.requests} · {stats.absent} empty
        </Row>
        <Row label="transferred">{formatBytes(stats.bytes)}</Row>
        <Row label="served from cache">
          {stats.hits} · {formatBytes(stats.hitBytes)}
        </Row>
        <Row label="layers drawn">{layers.length}</Row>
      </div>

      {status === "error" && (
        <p className="mb-4 border border-rule bg-panel px-3 py-2 font-mono text-[11px] text-papyrus">
          {error}
        </p>
      )}

      {layers.length === 0 && status !== "reading" && (
        <p className="caption text-[13px]">
          {target.kind === "sheet"
            ? "Build the sheet, then look for the layer where texture sharpens. That is the sheet face, and it is where ink would be."
            : "This is a raw scroll volume — the layers here are cross-sections through windings, not sheet faces. Nothing readable will appear. Kept for comparison."}
        </p>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {layers.map((l) => (
          <LayerTile
            key={l.index}
            index={l.index}
            image={l.image}
            active={selected === l.index}
            onClick={() => setSelected(selected === l.index ? null : l.index)}
          />
        ))}
      </div>
    </div>
  );
}

function LayerTile({
  index,
  image,
  active,
  onClick,
}: {
  index: number;
  image: ImageData;
  active: boolean;
  onClick: () => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    c.width = image.width;
    c.height = image.height;
    c.getContext("2d")?.putImageData(image, 0, 0);
  }, [image]);

  return (
    <button
      onClick={onClick}
      className="group text-left"
      style={{ outline: active ? "1px solid var(--color-ochre)" : undefined }}
    >
      <canvas
        ref={ref}
        className="block w-full border border-rule bg-black"
        style={{ imageRendering: "pixelated", aspectRatio: "1 / 1" }}
      />
      <p
        className={`mt-1 font-mono text-[10px] ${active ? "text-ochre" : "text-ash"} group-hover:text-ochre`}
      >
        layer {index}
      </p>
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="ledger-row">
      <span className="ledger-label">{label}</span>
      <span className="ledger-value font-mono text-[11px]">{children}</span>
    </div>
  );
}
