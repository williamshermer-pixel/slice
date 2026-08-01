"use client";

import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Cross-scan QC overlay for PHerc0139.
 *
 * The one thing here that does not exist elsewhere: where two scans of the same
 * papyrus, at different photon energies and through different ink recipes,
 * disagree about ink. Neuroglancer will show you a volume; nothing will show
 * you this.
 *
 * Assets are baked by tools/build_qc_assets.py. Each PNG carries the label CODE
 * in its red channel (0 unlabelled, 1 ink, 2 blank, 3 disputed) rather than a
 * colour, so the palette lives here and codes can be toggled without touching
 * the data. Green flags any block that contained a disputed pixel before
 * downsampling, so a 4x reduction cannot hide disagreement by out-voting it.
 */

type Seg = {
  segment: string;
  w: number;
  h: number;
  downsample: number;
  um_per_px: number;
  letter_px: number;
  pct: { unlabelled: number; ink: number; blank: number; disputed: number };
  shared_sheet_pct: number;
  pearson_r: number;
  jaccard: number;
  null: number;
  enrichment: number | null;
  p: number;
  registration: Record<string, number | string>;
  sources: Record<string, string>;
  surface_id: string;
  segment_full: string;
  clusters: { y: number; x: number; area_mm2: number; letters: number }[];
};

/**
 * The join. The published ink map is written on the surface volume's own
 * canvas, so a label pixel maps to the sheet by a pure scale -- no
 * registration. Verified across all 37 segments to within +/-16 px on canvases
 * of 20-40k px (~2% of a letter). Clusters in index.json are already in
 * surface level-0 space; a click on the canvas converts through the PNG's
 * downsample factor.
 *
 * The window is 6 letters across, wide enough to see whether a disagreement
 * sits on a text line or out on blank sheet.
 */
const LETTER_SURFACE_PX = 720; // 1.61 mm at 2.258 um/voxel

/**
 * Neuroglancer link onto the same sheet — BUILT, NOT SHIPPED.
 *
 * Their demo instance reads `zarr2://` from the Vesuvius bucket, which is
 * CORS-open, and it accepts this URL: the layer appears by name and the
 * position is taken. But every panel renders blank grey, so no link to it is
 * exposed in the UI.
 *
 * What is known: the volume exists (verified against the bucket), the
 * coordinates are right, and the same viewer renders the project's own
 * `volumes/*-masked.zarr` fine. The difference is that those are scroll
 * volumes while these are per-segment SURFACE volumes -- multiscale groups
 * with an anisotropic pyramid that keeps every sheet layer at every level.
 * That is the first thing to check when picking this up.
 *
 * Kept here because the URL construction is correct and only the rendering is
 * unresolved. A link that opens a grey void is worse than no link.
 */
const BUCKET =
  "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com";

function neuroglancerHref(seg: Seg, y: number, x: number) {
  const src = seg.sources["59keV"] ?? "";
  // "PHerc0139-<seg>-<volume>-<date>-<recipe>-tile...tif" -> the volume name
  const m = src.match(/-(1\.129um-[^-]*-[^-]*-volume-\d+-L1)-/);
  const vol = m ? `${m[1]}.zarr` : null;
  if (!vol) return null;
  const url = `${BUCKET}/PHerc0139/segments/${seg.segment_full}/surface-volumes/${vol}`;
  const state = {
    dimensions: { z: [1, ""], y: [1, ""], x: [1, ""] },
    position: [58, y, x],
    crossSectionScale: 2,
    layers: [
      {
        type: "image",
        source: `zarr2://${url}`,
        tab: "source",
        shader:
          "#uicontrol invlerp normalized\nvoid main() { emitGrayscale(normalized()); }",
        name: `0139-${seg.segment}`,
      },
    ],
    layout: "xy",
  };
  return `https://neuroglancer-demo.appspot.com/#!${encodeURIComponent(
    JSON.stringify(state),
  )}`;
}

function sheetHref(seg: Seg, y: number, x: number) {
  const win = Math.round(6 * LETTER_SURFACE_PX);
  const p = new URLSearchParams({
    src: "sheet",
    v: seg.surface_id,
    x: String(Math.max(0, Math.round(x - win / 2))),
    y: String(Math.max(0, Math.round(y - win / 2))),
    w: String(win),
    h: String(win),
    l: "1",
  });
  return `/viewer?${p.toString()}`;
}

const INK = [233, 229, 219] as const;      // papyrus
const DISPUTED = [200, 151, 31] as const;  // ochre
const BLANK = [38, 38, 43] as const;       // slate
const VOID = [10, 10, 11] as const;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule py-[5px]">
      <span className="eyebrow shrink-0">{label}</span>
      <span className="text-right font-mono text-[12px] text-papyrus">
        {children}
      </span>
    </div>
  );
}

export default function QCPage() {
  const [segs, setSegs] = useState<Seg[]>([]);
  const [i, setI] = useState(0);
  const [show, setShow] = useState({ ink: true, disputed: true, blank: true });
  const [err, setErr] = useState<string | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const raw = useRef<ImageData | null>(null);

  useEffect(() => {
    fetch("/qc/index.json")
      .then((r) => r.json())
      .then((d) => setSegs(d.segments))
      .catch((e) => setErr(String(e)));
  }, []);

  const seg = segs[i];

  // load the code image once per segment
  useEffect(() => {
    if (!seg) return;
    raw.current = null;
    const img = new Image();
    img.onload = () => {
      const off = document.createElement("canvas");
      off.width = img.width;
      off.height = img.height;
      const c = off.getContext("2d", { willReadFrequently: true });
      if (!c) return;
      c.drawImage(img, 0, 0);
      raw.current = c.getImageData(0, 0, img.width, img.height);
      paint();
    };
    img.onerror = () => setErr(`could not load /qc/${seg.segment}.png`);
    img.src = `/qc/${seg.segment}.png`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg?.segment]);

  function paint() {
    const src = raw.current;
    const cv = canvas.current;
    if (!src || !cv) return;
    cv.width = src.width;
    cv.height = src.height;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const out = ctx.createImageData(src.width, src.height);
    for (let p = 0; p < src.data.length; p += 4) {
      const code = src.data[p];
      const anyDisputed = src.data[p + 1] > 127;
      let col: readonly [number, number, number] = VOID;
      // Precedence matters. The disputed flag exists so downsampling cannot
      // vote disagreement away, but letting it override INK hides the
      // agreement cores entirely: a confirmed letter is usually ringed by
      // disputed pixels, so every letter rendered as solid ochre. Ink wins
      // where ink exists; the flag only promotes blank/unlabelled to disputed.
      if (code === 1 && show.ink) col = INK;
      else if ((code === 3 || anyDisputed) && show.disputed) col = DISPUTED;
      else if (code === 2 && show.blank) col = BLANK;
      else if (code !== 0) col = BLANK;
      out.data[p] = col[0];
      out.data[p + 1] = col[1];
      out.data[p + 2] = col[2];
      out.data[p + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
  }

  useEffect(paint, [show, seg]);

  const worst = useMemo(
    () => segs.slice(0, 5).map((s) => s.segment),
    [segs]
  );

  return (
    <main className="mx-auto max-w-[1240px] px-6 py-7">
      <header className="mb-6 border-b border-rule pb-4">
        <p className="eyebrow mb-1">PHerc0139 · 59 keV vs 78 keV</p>
        <h1 className="font-display text-[2.6rem] leading-none tracking-tight text-papyrus">
          Where the two scans disagree
        </h1>
        <p className="caption mt-2 max-w-[74ch] text-[13px]">
          This scroll was scanned at two X-ray energies and an ink map was
          published from each, months apart, with different recipes. Every
          segment below shows where they agree, where only one of them calls
          ink, and where both are silent. If you are drawing labels over a
          single published map, the ochre is where that map is least safe to
          trust.
        </p>
      </header>

      {err && (
        <p className="mb-4 border border-rule bg-panel p-3 font-mono text-[12px] text-ochre">
          {err}
        </p>
      )}

      {!segs.length && !err && (
        <p className="caption text-[13px]">loading segment index…</p>
      )}

      {seg && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <button
                className="border border-rule px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ash hover:text-papyrus"
                onClick={() => setI((v) => (v - 1 + segs.length) % segs.length)}
              >
                ← prev
              </button>
              <select
                className="border border-rule bg-panel px-2 py-1 font-mono text-[11px] text-papyrus"
                value={i}
                onChange={(e) => setI(Number(e.target.value))}
              >
                {segs.map((s, n) => (
                  <option key={s.segment} value={n}>
                    {s.segment} — {s.pct.disputed.toFixed(2)}% disputed
                  </option>
                ))}
              </select>
              <button
                className="border border-rule px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ash hover:text-papyrus"
                onClick={() => setI((v) => (v + 1) % segs.length)}
              >
                next →
              </button>
              <span className="ml-2 font-mono text-[11px] text-ash">
                {i + 1} / {segs.length} · sorted by disagreement
              </span>
            </div>

            <div className="mb-3 flex flex-wrap gap-2">
              {(
                [
                  ["ink", "both scans call ink", INK],
                  ["disputed", "only one scan", DISPUTED],
                  ["blank", "neither scan", BLANK],
                ] as const
              ).map(([k, label, col]) => (
                <button
                  key={k}
                  onClick={() => setShow((s) => ({ ...s, [k]: !s[k] }))}
                  className={`flex items-center gap-2 border px-2 py-1 font-mono text-[11px] uppercase tracking-wider ${
                    show[k as keyof typeof show]
                      ? "border-ochre text-papyrus"
                      : "border-rule text-ash line-through"
                  }`}
                >
                  <span
                    className="inline-block h-[10px] w-[10px] border border-rule"
                    style={{ background: `rgb(${col.join(",")})` }}
                  />
                  {label}
                </button>
              ))}
            </div>

            <div className="border border-rule bg-void p-2">
              <canvas
                ref={canvas}
                className="block h-auto w-full cursor-crosshair"
                title="click anywhere to open that spot on the sheet"
                onClick={(e) => {
                  const cv = e.currentTarget;
                  const r = cv.getBoundingClientRect();
                  const px = ((e.clientX - r.left) / r.width) * cv.width;
                  const py = ((e.clientY - r.top) / r.height) * cv.height;
                  const f = seg.downsample * 8; // png -> surface level 0
                  window.open(
                    sheetHref(seg, Math.round(py * f), Math.round(px * f)),
                    "_blank",
                  );
                }}
              />
            </div>
            <p className="caption mt-2 text-[12px]">
              <span className="text-ochre">
                Click anywhere on the map to open that exact spot on the
                papyrus.
              </span>{" "}
              {seg.um_per_px} µm/px at this zoom (1/{seg.downsample} of the
              label grid) · one letter ≈ {seg.letter_px} px. Any block holding a
              disputed pixel is drawn disputed, so reducing resolution cannot
              hide disagreement.
            </p>
          </div>

          <aside>
            <p className="eyebrow mb-2">This segment</p>
            <div className="ledger">
              <Row label="both scans call ink">{seg.pct.ink.toFixed(2)}%</Row>
              <Row label="only one scan">{seg.pct.disputed.toFixed(2)}%</Row>
              <Row label="neither scan">{seg.pct.blank.toFixed(2)}%</Row>
              <Row label="shared sheet">{seg.shared_sheet_pct}%</Row>
            </div>

            <p className="eyebrow mb-2 mt-6">Agreement, measured</p>
            <div className="ledger">
              <Row label="high-passed pearson r">{seg.pearson_r}</Row>
              <Row label="jaccard">{seg.jaccard}</Row>
              <Row label="vs spatial null">{seg.null}</Row>
              <Row label="enrichment">
                {seg.enrichment === null ? "undefined" : `${seg.enrichment}×`}
              </Row>
              <Row label="p (24-roll floor)">{seg.p}</Row>
            </div>

            <p className="eyebrow mb-2 mt-6">Registration applied</p>
            <div className="ledger">
              <Row label="blocks trusted">
                {String(seg.registration.blocks_trusted ?? "—")} /{" "}
                {String(seg.registration.blocks_total ?? "—")}
              </Row>
              <Row label="median dy · dx">
                {String(seg.registration.median_dy_px ?? "—")} ·{" "}
                {String(seg.registration.median_dx_px ?? "—")} px
              </Row>
              <Row label="iqr dy · dx">
                {String(seg.registration.iqr_dy_px ?? "—")} ·{" "}
                {String(seg.registration.iqr_dx_px ?? "—")} px
              </Row>
            </div>

            <p className="mt-6 max-w-[42ch] text-[12px] leading-relaxed text-ash">
              Two bounds. The two recipes are plausibly entangled through
              training data, so agreement may partly be shared model lineage
              rather than shared ink. And 1.1 µm data is cleaner than 2.4 µm by
              the project&apos;s own measurement, so some disagreement is
              resolution, not error. This is cross-energy and cross-recipe, not
              independent.
            </p>
            <p className="mt-3 max-w-[42ch] text-[12px] leading-relaxed text-ash">
              Method, per-segment numbers and the failure catalog:{" "}
              <a className="text-ochre underline" href="/record">
                the record
              </a>
              .
            </p>
          </aside>
        </div>
      )}

      {seg && seg.clusters.length > 0 && (
        <section className="mt-10 border-t border-rule pt-5">
          <p className="eyebrow mb-1">
            Work queue · biggest disagreements on this segment
          </p>
          <p className="caption mb-3 max-w-[74ch] text-[12px]">
            Contiguous regions only one scan calls, largest first, sized in
            letters. Each opens the sheet at that spot so you can judge it
            against the papyrus rather than against a colour.
          </p>
          <div className="ledger">
            {seg.clusters.map((c, n) => (
              <div
                key={n}
                className="flex items-baseline justify-between gap-4 border-b border-rule py-[6px] hover:bg-panel"
              >
                <span className="eyebrow shrink-0">
                  {String(n + 1).padStart(2, "0")} · {c.letters} letters²
                </span>
                <span className="font-mono text-[12px] text-ash">
                  {c.area_mm2} mm² · y {c.y} x {c.x}
                  <a
                    className="ml-3 text-ochre underline"
                    href={sheetHref(seg, c.y, c.x)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    our viewer ↗
                  </a>
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {worst.length > 0 && (
        <section className="mt-8 border-t border-rule pt-5">
          <p className="eyebrow mb-2">Most disputed segments on this scroll</p>
          <div className="flex flex-wrap gap-2">
            {worst.map((sg) => (
              <button
                key={sg}
                onClick={() => setI(segs.findIndex((x) => x.segment === sg))}
                className="border border-rule px-2 py-1 font-mono text-[11px] text-ash hover:text-papyrus"
              >
                {sg}
              </button>
            ))}
          </div>
        </section>
      )}

    </main>
  );
}
