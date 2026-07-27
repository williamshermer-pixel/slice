/**
 * Catalog of scroll volumes.
 *
 * The first thirteen are the scrolls eligible for the 2027 Grand Prize — and
 * each is also worth a $50,000 First Letters prize to whoever first recovers
 * ten legible letters from a single 4 cm² patch. None of them have been read.
 * That is the reason this list is the catalog rather than a demo dataset.
 *
 * Every entry below was checked against live S3 in July 2026: `.zattrs` returns
 * 200, the OME `multiscales` attribute is present, and each volume carries
 * exactly six pyramid levels of uncompressed 8-bit data chunked at 128^3.
 *
 * Shapes are [z, y, x] at level 0, transcribed from each `0/.zarray`. They are
 * here so the UI can tell you what you are about to open before it opens it —
 * PHerc. 332 alone is 8.3 TB at full resolution.
 */

const BUCKET = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com";

export type VolumeEntry = {
  id: string;
  label: string;
  /** Where to read it. */
  url: string;
  /** Whether text has ever been recovered from this scroll. */
  unread: boolean;
  /** Scan resolution in micrometres, taken from the volume ID. */
  voxelUm: number;
  /** [z, y, x] at level 0. */
  shape: [number, number, number];
};

function volume(sample: string, file: string): string {
  return `${BUCKET}/${sample}/volumes/${file}`;
}

export const VOLUMES: VolumeEntry[] = [
  {
    id: "PHerc0125",
    label: "PHerc. 125",
    url: volume("PHerc0125", "20250821151825-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [20840, 8387, 8387],
  },
  {
    id: "PHerc0191",
    label: "PHerc. 191",
    url: volume("PHerc0191", "20250821151635-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [18977, 8387, 8387],
  },
  {
    id: "PHerc0211",
    label: "PHerc. 211",
    url: volume("PHerc0211", "20250821151803-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [19416, 7948, 7948],
  },
  {
    id: "PHerc0257",
    label: "PHerc. 257",
    url: volume("PHerc0257", "20250821151750-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [18872, 8388, 8388],
  },
  {
    id: "PHerc0268",
    label: "PHerc. 268",
    url: volume("PHerc0268", "20251110183117-8.640um-1.2m-116keV-masked.zarr"),
    unread: true,
    voxelUm: 8.64,
    shape: [14833, 12145, 12145],
  },
  {
    id: "PHerc0358",
    label: "PHerc. 358",
    url: volume("PHerc0358", "20250821151737-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [14744, 7783, 7783],
  },
  {
    id: "PHerc0800",
    label: "PHerc. 800",
    url: volume("PHerc0800", "20250521135224-8.640um-1.2m-116keV-masked.zarr"),
    unread: true,
    voxelUm: 8.64,
    shape: [24298, 9867, 9867],
  },
  {
    id: "PHerc0813",
    label: "PHerc. 813",
    url: volume("PHerc0813", "20250821151723-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [16993, 7947, 7947],
  },
  {
    id: "PHerc0826",
    label: "PHerc. 826",
    url: volume("PHerc0826", "20250821151701-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [16920, 8169, 8169],
  },
  {
    id: "PHerc1203",
    label: "PHerc. 1203",
    url: volume("PHerc1203", "20250820131727-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [18977, 6844, 6844],
  },
  {
    id: "PHerc1218",
    label: "PHerc. 1218",
    url: volume("PHerc1218", "20250521120456-8.640um-1.2m-116keV-masked.zarr"),
    unread: true,
    voxelUm: 8.64,
    shape: [23247, 7593, 7593],
  },
  {
    id: "PHerc1447",
    label: "PHerc. 1447",
    url: volume("PHerc1447", "20250521151220-8.640um-1.2m-116keV-masked.zarr"),
    unread: true,
    voxelUm: 8.64,
    shape: [24297, 8343, 8343],
  },
  {
    id: "PHerc1545",
    label: "PHerc. 1545",
    url: volume("PHerc1545", "20250821151648-9.362um-1.2m-113keV-masked.zarr"),
    unread: true,
    voxelUm: 9.362,
    shape: [20961, 7506, 7506],
  },
  {
    // The transcribed 2023 path (20231201141544-3.240um-70keV) is gone from the
    // bucket — 404. This is the December 2025 rescan at 2.399um, found by
    // listing `PHerc0332/volumes/`, which the bucket permits anonymously.
    id: "PHerc0332",
    label: "PHerc. 332",
    url: volume("PHerc0332", "20251211183505-2.399um-0.2m-78keV-masked.zarr"),
    unread: false,
    voxelUm: 2.399,
    shape: [33592, 15761, 15761],
  },
];

export function findVolume(id: string): VolumeEntry | undefined {
  return VOLUMES.find((v) => v.id === id);
}
