#!/usr/bin/env python3
"""POSITIVE CONTROL ON THE WHOLE PIPELINE — runs ON the pod.

THE QUESTION. Every ink search this project has run came back empty. That is
either a fact about the papyrus or a fact about our pipeline, and nothing built
so far can tell the two apart: our controls test the DETECTOR, never the chain
that feeds it.

So: take Vesuvius Challenge's own cross-segment baseline model, feed it their
own published surface volume, and see whether it reproduces their own published
ink map. Every component is theirs. If it lands, our reading of the data format
is correct and the negatives stand. If it comes back empty on a sheet with
known readable Greek, the fault is ours and every search we ran measured a bug.

WHY iteration-0 AND NOT iteration-5. The six PHerc.1667 checkpoints differ only
in supervision. iteration-5 is the far end of a pseudo-label loop their own
ablation shows SATURATING — and it is what this project fine-tuned from, which
was a mistake. iteration-0 is the cross-segment baseline: trained on
500p2a + 658 + two auto-grown segments, with NO labels from the target segment.
It is the closest published thing to the generalist model that made letters
appear in Scroll 4 with no scroll-specific labelling at all.

THE CONTRACT (from the model card, not guessed):
    input   (B, 1, 62, 256, 256) float32
    prep    clip raw uint8 to [0, 200], then / 255
    window  256, stride 128
    output  sigmoid at quarter res (64x64) -> upsample x4 -> average overlaps

TARGET. Scroll 1 segment 20231005123336 — the sheet the 2023 Grand Prize text
was read from, at 2.4 um, where a 3.00 mm hand makes letterforms unambiguous.
The crop is a text column verified by eye against the published map.

READ BEFORE CHANGING
--------------------
  62 of 109        The surface volume is 109 layers deep and the sheet sits at
                   the middle. Their convention is a band CENTRED on the sheet
                   (65 layers with 32.tif on the segmentation line; 157 at
                   3.24 um) -- a fixed ~510 um span, layer count falling out of
                   voxel size. So take layers 24..85, centred on 54. Taking the
                   first 62 would look identical in shape and be wrong.

  uncompressed     Surface volumes are uint8, compressor null,
                   dimension_separator "/". Chunks are [depth,128,128] -- the
                   WHOLE depth stack of a tile in one object -- so plain HTTP
                   chunk reads work and no zarr dependency is needed.

  sparse           Chunks outside the mask were never written; S3 404s. Absent
                   is not an error, it is empty space.
"""
import concurrent.futures as cf
import io
import json
import os
import urllib.error
import urllib.request

import numpy as np

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
UA = {"User-Agent": "Mozilla/5.0"}
OUT = "/workspace/out"
MODEL = "scrollprize/PHerc.1667-iteration-0"

SEG = "PHercParis4/segments/20231005123336"
VOL = f"{B}/{SEG}/surface-volumes/2.4um-0.22m-78keV-volume-20260411134726.zarr"
INK = (f"{B}/{SEG}/ink-detection/downsampled/PHercParis4-20231005123336-2.4um-"
       "0.22m-78keV-volume-20260411134726-20260417190342-"
       "new_canon_autoresearch_recipe-tile256-stride128-ds8.jpg")

# Level-0 crop, chosen off the published map as a dense text column.
X0, Y0, CW, CH = 28800, 1200, 4096, 4096
D = 62
WINDOW, STRIDE = 256, 128
CLIP = 200


def get(url, timeout=300):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def fetch_stack():
    """(CH, CW, D) uint8 — the 62-layer band centred on the sheet."""
    za = json.loads(get(f"{VOL}/0/.zarray").decode())
    depth, height, width = za["shape"]
    cz, cy, cx = za["chunks"]
    assert za["dtype"] == "|u1" and za["compressor"] is None, za
    lo = (depth - D) // 2
    hi = lo + D
    print(f"volume {za['shape']} chunks {za['chunks']} -> layers {lo}..{hi-1}",
          flush=True)

    out = np.zeros((CH, CW, D), np.uint8)
    i0, i1 = Y0 // cy, -(-(Y0 + CH) // cy)
    j0, j1 = X0 // cx, -(-(X0 + CW) // cx)
    jobs = [(i, j) for i in range(i0, i1) for j in range(j0, j1)]
    print(f"{len(jobs)} chunks to read", flush=True)

    def one(job):
        i, j = job
        try:
            raw = get(f"{VOL}/0/0/{i}/{j}")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return i, j, None
            raise
        a = np.frombuffer(raw, np.uint8)
        if a.size != cz * cy * cx:
            return i, j, None
        return i, j, a.reshape(cz, cy, cx)[lo:hi]

    got = 0
    with cf.ThreadPoolExecutor(24) as ex:
        for i, j, blk in ex.map(one, jobs):
            if blk is None:
                continue
            got += 1
            gy, gx = i * cy - Y0, j * cx - X0
            ys, ye = max(0, gy), min(CH, gy + cy)
            xs, xe = max(0, gx), min(CW, gx + cx)
            if ye <= ys or xe <= xs:
                continue
            out[ys:ye, xs:xe] = blk[:, ys - gy:ye - gy, xs - gx:xe - gx].transpose(1, 2, 0)
    print(f"{got}/{len(jobs)} chunks stored (rest sparse)", flush=True)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel

    stack = fetch_stack()
    np.save(f"{OUT}/stack_meta.npy", np.array(stack.shape))
    fmask = (stack.max(axis=2) > 0).astype(np.uint8) * 255
    print("sheet coverage %.1f%%" % (100 * (fmask > 0).mean()), flush=True)

    print("loading", MODEL, flush=True)
    model = AutoModel.from_pretrained(MODEL, trust_remote_code=True).eval()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(dev)
    print("device", dev, flush=True)

    pred = np.zeros((CH, CW), np.float32)
    cnt = np.zeros((CH, CW), np.float32)
    n = 0
    with torch.no_grad():
        for y in range(0, CH - WINDOW + 1, STRIDE):
            for x in range(0, CW - WINDOW + 1, STRIDE):
                if np.any(fmask[y:y + WINDOW, x:x + WINDOW] == 0):
                    continue
                tile = stack[y:y + WINDOW, x:x + WINDOW]          # (256,256,62)
                t = np.clip(tile, 0, CLIP).astype(np.float32) / 255.0
                t = torch.from_numpy(t).permute(2, 0, 1)[None, None].to(dev)
                p = torch.sigmoid(model(t).logits)
                p = F.interpolate(p, scale_factor=4, mode="bilinear")
                pred[y:y + WINDOW, x:x + WINDOW] += p.squeeze().float().cpu().numpy()
                cnt[y:y + WINDOW, x:x + WINDOW] += 1.0
                n += 1
    print(f"{n} tiles inferred", flush=True)
    ours = np.divide(pred, cnt, out=np.zeros_like(pred), where=cnt != 0)
    np.save(f"{OUT}/ours.npy", ours)

    # Their published map, same crop, for the agreement number.
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    theirs_full = np.array(Image.open(io.BytesIO(get(INK))))
    if theirs_full.ndim == 3:
        theirs_full = theirs_full[..., 0]
    ds = 8
    theirs = theirs_full[Y0 // ds:(Y0 + CH) // ds, X0 // ds:(X0 + CW) // ds]
    ours_ds = ours.reshape(CH // ds, ds, CW // ds, ds).mean(axis=(1, 3))
    np.save(f"{OUT}/theirs.npy", theirs)

    m = cnt.reshape(CH // ds, ds, CW // ds, ds).max(axis=(1, 3)) > 0
    res = {"tiles": n, "crop": [X0, Y0, CW, CH], "layers": D, "model": MODEL,
           "coverage_pct": round(float(100 * (fmask > 0).mean()), 2)}
    if m.sum() > 100:
        a, b = ours_ds[m].ravel(), theirs[m].ravel().astype(np.float32)
        res["pearson_r"] = round(float(np.corrcoef(a, b)[0, 1]), 4)
        hi = b >= np.percentile(b, 90)
        lo_ = b <= np.percentile(b, 50)
        if hi.sum() > 10 and lo_.sum() > 10:
            pos, neg = a[hi], a[lo_]
            allv = np.concatenate([pos, neg])
            order = allv.argsort()
            rank = np.empty(len(allv)); rank[order] = np.arange(1, len(allv) + 1)
            auc = (rank[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
            res["auc_vs_their_calls"] = round(float(auc), 4)
        res["ours_mean"] = round(float(a.mean()), 4)
        res["ours_p99"] = round(float(np.percentile(a, 99)), 4)
    json.dump(res, open(f"{OUT}/control.json", "w"), indent=1)
    print(json.dumps(res, indent=1), flush=True)

    for nm, arr in (("ours", ours_ds), ("theirs", theirs.astype(np.float32))):
        v = arr[m] if m.sum() else arr.ravel()
        if v.size:
            lo2, hi2 = np.percentile(v, 1), np.percentile(v, 99)
            img = np.clip((arr - lo2) * 255.0 / max(hi2 - lo2, 1e-6), 0, 255)
            Image.fromarray(img.astype(np.uint8)).save(f"{OUT}/{nm}.png")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
