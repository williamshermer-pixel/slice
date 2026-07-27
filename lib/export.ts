import { scaleBar } from "./colormaps";

/**
 * Writes the current view to a PNG with its provenance burned into the image.
 *
 * A screenshot of a CT slice with no caption is close to worthless in an
 * argument: nobody can tell which scroll it is, how deep, how big, or how hard
 * the contrast was pushed. Every exported frame therefore carries the scroll,
 * the slice, the crop, the display window, the LUT and a scale bar — so the
 * image survives being pasted somewhere with no context attached, which is the
 * only way images ever travel.
 */
export type ExportCaption = {
  scroll: string;
  level: string;
  z: number;
  x: number;
  y: number;
  width: number;
  height: number;
  window: [number, number];
  colormap: string;
  voxelUm: number;
  url: string;
};

const PAPYRUS = "#e9e5db";
const ASH = "#8b8b94";
const VOID = "#0a0a0b";
const OCHRE = "#c8971f";

export async function exportPng(
  source: HTMLCanvasElement,
  caption: ExportCaption,
): Promise<void> {
  const pad = 28;
  const captionH = 132;
  const w = source.width;
  const h = source.height;

  // Upscale small crops so the caption stays legible next to the plate.
  const scale = Math.max(1, Math.round(720 / Math.max(w, h)));
  const iw = w * scale;
  const ih = h * scale;

  const out = document.createElement("canvas");
  out.width = iw + pad * 2;
  out.height = ih + pad + captionH;
  const ctx = out.getContext("2d");
  if (!ctx) throw new Error("Could not get a 2D context for the export canvas.");

  ctx.fillStyle = VOID;
  ctx.fillRect(0, 0, out.width, out.height);

  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(source, 0, 0, w, h, pad, pad, iw, ih);

  ctx.strokeStyle = "#26262b";
  ctx.lineWidth = 1;
  ctx.strokeRect(pad + 0.5, pad + 0.5, iw - 1, ih - 1);

  // Scale bar, sitting inside the plate at the bottom left.
  const bar = scaleBar(caption.width, caption.voxelUm);
  const barPx = Math.min(iw * bar.fraction, iw - 40);
  const bx = pad + 16;
  const by = pad + ih - 22;
  ctx.fillStyle = "rgba(10,10,11,0.72)";
  ctx.fillRect(bx - 8, by - 16, barPx + 16, 30);
  ctx.strokeStyle = PAPYRUS;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(bx, by);
  ctx.lineTo(bx + barPx, by);
  ctx.moveTo(bx, by - 5);
  ctx.lineTo(bx, by + 5);
  ctx.moveTo(bx + barPx, by - 5);
  ctx.lineTo(bx + barPx, by + 5);
  ctx.stroke();
  ctx.fillStyle = PAPYRUS;
  ctx.font = "500 12px ui-monospace, SFMono-Regular, monospace";
  ctx.fillText(bar.label, bx, by - 8);

  // Caption block.
  let ty = pad + ih + 34;
  ctx.fillStyle = PAPYRUS;
  ctx.font = "600 19px ui-monospace, SFMono-Regular, monospace";
  ctx.fillText(caption.scroll, pad, ty);

  ctx.fillStyle = OCHRE;
  ctx.font = "500 12px ui-monospace, SFMono-Regular, monospace";
  ctx.fillText("SLICE", out.width - pad - ctx.measureText("SLICE").width, ty);

  ty += 24;
  ctx.fillStyle = ASH;
  ctx.font = "400 12px ui-monospace, SFMono-Regular, monospace";
  const lines = [
    `level ${caption.level}  ·  z ${caption.z}  ·  crop ${Math.round(caption.x)},${Math.round(caption.y)} ${Math.round(caption.width)}×${Math.round(caption.height)} voxels  ·  ${caption.voxelUm} µm/voxel`,
    `window ${caption.window[0]}–${caption.window[1]}  ·  LUT ${caption.colormap}  ·  false colour is a reading aid, not evidence`,
    caption.url,
  ];
  for (const line of lines) {
    ctx.fillText(line, pad, ty);
    ty += 18;
  }

  const blob = await new Promise<Blob | null>((resolve) =>
    out.toBlob(resolve, "image/png"),
  );
  if (!blob) throw new Error("Could not encode the PNG.");

  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = `${caption.scroll.replace(/[^\w]+/g, "")}-z${caption.z}-${Math.round(caption.x)}x${Math.round(caption.y)}.png`;
  a.click();
  URL.revokeObjectURL(href);
}
