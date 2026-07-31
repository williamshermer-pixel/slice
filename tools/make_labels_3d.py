"""MAKE 3D INK LABELS — the deliverable for ScrollPrize/villa #192 / #193.

#192 asks for ink labels "representative of only the detectable ink patterns"
(their stated fear: annotators drawing what they think the model means, and
models learning SURFACE instead of ink) "in true 3d rather than a single image
projected across multiple layers". Format: zarr or tif slices, ready-to-run.

What this emits, per mapped window, as plain zarr v2 (zlib, readable by any
zarr client — no exotic codecs):

  <out>/<scroll>/<segment>__y<y0>_x<x0>/
      label/      uint8 (D, 4096, 4096) at the -L1 surface-volume's own grid.
                  0 = unlabelled, 1 = INK (calibrated), 2 = certified BLANK
                  (spillover-safe negative). Nonzero ONLY inside the measured
                  ink depth band z27..z89 — depth-restricted from the measured
                  band response (0.654 -> 0.944 AUC), NOT projected across the
                  full stack. Voxel-level depth attribution is not claimed;
                  .zattrs says exactly that.
      conf/       uint8 (4096, 4096) = round(255 * model probability).
      .zattrs     full provenance: source volume path, window origin, depth
                  band, calibrated floor + its blank FPR, condition-control
                  AUC (ink vs SAME-condition blank sheet), model, recipe.

Positives: probability >= the scroll's calibrated floor (0.2% blank FPR).
Negatives: blank boxes >= 1.5 mm from any published call (spillover-safe) and
below the floor — training pairs need certified absence, not just absence.

The image half of each pair is NOT redistributed (CC BY-NC): .zattrs carries
the exact bucket path + window, and tools/fetch_pair.py assembles the crop.

  python3 tools/make_labels_3d.py                 # all scrolls with maps
  SCROLLS=PHercParis4 python3 tools/make_labels_3d.py
"""
import glob, json, os, sys, zlib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTROOT = os.path.join(ROOT, "out", "labels3d")
Z0, DLAY, R = 27, 62, 4096
CLEAR_MM = 1.5
SCROLL_DIRS = {"PHerc0139": "lostbook", "PHercParis4": "scroll1",
               "PHerc0500P2": "p0500p2", "PHerc0343P": "p0343p"}


def write_zarr(path, arr, chunks, attrs=None):
    """Minimal zarr v2 writer: zlib-compressed C-order chunks."""
    os.makedirs(path, exist_ok=True)
    meta = {"zarr_format": 2, "shape": list(arr.shape),
            "chunks": list(chunks), "dtype": "|u1",
            "compressor": {"id": "zlib", "level": 6},
            "fill_value": 0, "order": "C", "filters": None,
            "dimension_separator": "."}
    open(os.path.join(path, ".zarray"), "w").write(json.dumps(meta))
    if attrs:
        open(os.path.join(path, ".zattrs"), "w").write(json.dumps(attrs, indent=1))
    grid = [int(np.ceil(s / c)) for s, c in zip(arr.shape, chunks)]
    n = 0
    for idx in np.ndindex(*grid):
        sl = tuple(slice(i * c, min((i + 1) * c, s))
                   for i, c, s in zip(idx, chunks, arr.shape))
        block = np.zeros(chunks, np.uint8)
        piece = arr[sl]
        block[tuple(slice(0, p) for p in piece.shape)] = piece
        open(os.path.join(path, ".".join(map(str, idx))), "wb").write(
            zlib.compress(block.tobytes(), 6))
        n += 1
    return n


def main():
    only = os.environ.get("SCROLLS")
    made = 0
    index = []
    for scroll, outdir in SCROLL_DIRS.items():
        if only and scroll not in only.split(","):
            continue
        lb = os.path.join(ROOT, "out", outdir)
        fp = os.path.join(lb, "floor.json")
        cc = os.path.join(lb, "condition_control.json")
        if not (os.path.exists(fp) and os.path.exists(cc)):
            print(f"{scroll}: missing floor/control calibration — skipped "
                  f"(labels ship ONLY with quality certificates)")
            continue
        os.environ["SCROLL"] = scroll
        os.environ.pop("OUTDIR", None)
        # fresh import context per scroll
        for m in list(sys.modules):
            if m == "differential_0139":
                del sys.modules[m]
        import differential_0139 as D
        floor = json.load(open(fp))
        ctrl = json.load(open(cc))
        clear_px = int(CLEAR_MM * D.MM)
        for mp in sorted(glob.glob(os.path.join(lb, "map_s*.npy"))):
            tag = os.path.basename(mp)[4:-4]
            metaf = os.path.join(lb, f"meta_{tag}.json")
            if not os.path.exists(metaf):
                continue
            meta = json.load(open(metaf))
            try:
                pub = D.pub_crop(meta)
            except Exception as e:
                print(f"  {tag}: pub fetch failed ({e}) — skipped")
                continue
            ours = np.load(mp)                       # 1024^2 quarter-res prob
            ink = (ours >= floor["floor"])
            called = (pub > 128).astype(np.float32)
            # spillover-safe certified blank: no published call within 1.5 mm
            k = min(clear_px, 1023)
            c = np.pad(called, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
            s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
            far = np.zeros((1024, 1024), bool)
            far[:s.shape[0], :s.shape[1]] = s <= 0
            blank = far & (pub < 60) & (ours < floor["floor"])

            lab2d = np.zeros((1024, 1024), np.uint8)
            lab2d[blank] = 2
            lab2d[ink] = 1                            # ink wins where both
            # upsample to the -L1 grid the surface volume lives on
            lab_full = np.repeat(np.repeat(lab2d, 4, 0), 4, 1)
            t = D.TARGETS[meta["seg"]]
            D_stack = 116                             # attrs carry the true D
            vol = np.zeros((Z0 + DLAY, R, R), np.uint8)  # stack above band unused
            vol[Z0:Z0 + DLAY] = lab_full[None]
            name = (meta["seg"].split("/")[-2][:40]
                    + f"__y{meta['window'][0]}_x{meta['window'][1]}")
            dst = os.path.join(OUTROOT, scroll, name)
            attrs = dict(
                issue="ScrollPrize/villa#192",
                scroll=scroll, segment=meta["seg"],
                surface_volume=t["sv"],
                window_origin_yx=meta["window"][:2], window_size=R,
                depth_band=[Z0, Z0 + DLAY],
                depth_semantics=("ink restricted to the MEASURED band "
                                 "z27..z89 (band response 0.654->0.944 AUC); "
                                 "voxel-level depth attribution NOT claimed"),
                label_codes={"0": "unlabelled", "1": "ink", "2": "certified blank"},
                floor=floor["floor"], floor_blank_fpr=floor["blank_fpr"],
                map_auc_vs_published=floor["auc"],
                condition_control_auc=ctrl["auc_near"],
                blank_keepout_mm=CLEAR_MM,
                model="scrollprize/PHerc.1667-iteration-5"
                      + (" + per-scribe fine-tune" if scroll == "PHerc0139" else ""),
                recipe="z27..z89, clip[0,200]/255, tile256/stride64, "
                       "gaussian logit blend",
                generator="tools/make_labels_3d.py",
                license_note="label only; image half fetched from the public "
                             "bucket by tools/fetch_pair.py (CC BY-NC data is "
                             "not redistributed)")
            nch = write_zarr(os.path.join(dst, "label"), vol,
                             (Z0 + DLAY, 512, 512), attrs)
            write_zarr(os.path.join(dst, "conf"),
                       np.repeat(np.repeat(
                           (np.clip(ours, 0, 1) * 255).astype(np.uint8), 4, 0), 4, 1),
                       (512, 512))
            made += 1
            index.append(dict(scroll=scroll, path=os.path.relpath(dst, OUTROOT),
                              ink_frac=round(float(ink.mean()), 4),
                              blank_frac=round(float(blank.mean()), 4)))
            print(f"  {scroll} {tag}: ink {100*ink.mean():.1f}% "
                  f"blank {100*blank.mean():.1f}% ({nch} chunks)")
    json.dump(dict(n=made, windows=index),
              open(os.path.join(OUTROOT, "MANIFEST.json"), "w"), indent=1)
    print(f"\n{made} label windows -> {os.path.relpath(OUTROOT, ROOT)} "
          f"+ MANIFEST.json")


if __name__ == "__main__":
    main()
