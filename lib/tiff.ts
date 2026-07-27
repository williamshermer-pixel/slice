/**
 * Minimal uncompressed 8-bit grayscale TIFF encoder.
 *
 * The ask in villa#192 is "ready-to-run" labels as zarr or .tif. A PNG plus a
 * note saying "convert this yourself" is not ready to run, and the browser has
 * no TIFF encoder, so here is one. Uncompressed single-strip baseline TIFF is
 * about ninety lines and is read by everything — PIL, tifffile, ImageJ, nnUNet
 * loaders — without an extra dependency on either end.
 *
 * Little-endian. Layout is header, then pixel data, then the IFD, which keeps
 * the strip offset trivially computable.
 */

const HEADER_BYTES = 8;

type Entry = { tag: number; type: number; count: number; value: number };

const SHORT = 3;
const LONG = 4;

export function encodeGrayTiff(
  pixels: Uint8Array,
  width: number,
  height: number,
): Uint8Array<ArrayBuffer> {
  if (pixels.length !== width * height) {
    throw new Error(
      `Pixel buffer is ${pixels.length} bytes, expected ${width * height} for ${width}×${height}.`,
    );
  }

  const dataOffset = HEADER_BYTES;
  const ifdOffset = dataOffset + pixels.length;

  const entries: Entry[] = [
    { tag: 256, type: LONG, count: 1, value: width }, // ImageWidth
    { tag: 257, type: LONG, count: 1, value: height }, // ImageLength
    { tag: 258, type: SHORT, count: 1, value: 8 }, // BitsPerSample
    { tag: 259, type: SHORT, count: 1, value: 1 }, // Compression: none
    { tag: 262, type: SHORT, count: 1, value: 1 }, // Photometric: BlackIsZero
    { tag: 273, type: LONG, count: 1, value: dataOffset }, // StripOffsets
    { tag: 277, type: SHORT, count: 1, value: 1 }, // SamplesPerPixel
    { tag: 278, type: LONG, count: 1, value: height }, // RowsPerStrip
    { tag: 279, type: LONG, count: 1, value: pixels.length }, // StripByteCounts
  ];

  const ifdBytes = 2 + entries.length * 12 + 4;
  // Built on an explicit ArrayBuffer so the result is a Blob-compatible view.
  const buffer = new ArrayBuffer(ifdOffset + ifdBytes);
  const out = new Uint8Array(buffer);
  const view = new DataView(buffer);

  // Header.
  out[0] = 0x49; // 'I'
  out[1] = 0x49; // 'I' — little-endian
  view.setUint16(2, 42, true);
  view.setUint32(4, ifdOffset, true);

  out.set(pixels, dataOffset);

  view.setUint16(ifdOffset, entries.length, true);
  let p = ifdOffset + 2;
  for (const e of entries) {
    view.setUint16(p, e.tag, true);
    view.setUint16(p + 2, e.type, true);
    view.setUint32(p + 4, e.count, true);
    // A SHORT occupies the first two bytes of the value field, not the last.
    if (e.type === SHORT) {
      view.setUint16(p + 8, e.value, true);
      view.setUint16(p + 10, 0, true);
    } else {
      view.setUint32(p + 8, e.value, true);
    }
    p += 12;
  }
  view.setUint32(p, 0, true); // no next IFD

  return out;
}

export function downloadBlob(data: BlobPart, filename: string, type: string): void {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
