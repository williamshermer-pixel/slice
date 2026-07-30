"""POD JOB — runs ON the RunPod 4090 at boot. Self-contained: streams the
segment from the public S3 bucket, runs scrollprize/PHerc.1667-iteration-0
on a 4096 px (9.2 mm) ink-aimed window using the validated convention
(layers 0..62, no flip, clip[0,200]/255, tile 256, stride 128), writes
side-by-side render + prediction + metrics to /workspace/out, which a
sibling http.server serves on port 8000.
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
import numpy as np

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
SEG = "PHerc1667/segments/20240304141531-w013_20240304141531_flatboi/"
SV = SEG + "surface-volumes/1.129um-0.22m-59keV-volume-20260323082859-L1.zarr/"
INK = SEG + ("ink-detection/downsampled/PHerc1667-20240304141531-1.129um-0.22m-"
             "59keV-volume-20260323082859-L1-20260709123958-mrg20736-1um-s1z2-"
             "tile256-stride128-ds8.jpg")
OUT = "/workspace/out"
REGION = 4096          # px at 2.258 um = 9.2 mm
DLAY, WINDOW, STRIDE, CH = 62, 256, 64, 128   # stride 64 = 8x oversample
os.makedirs(OUT, exist_ok=True)


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=90):
    return urllib.request.urlopen(u, timeout=t).read()


def main():
    from PIL import Image, ImageDraw
    log("fetching metadata + ink map")
    za = json.loads(get(f"{B}/{SV}0/.zarray").decode())
    D, HH, WW = za["shape"]
    ink = np.array(Image.open(io.BytesIO(get(f"{B}/{INK}")))).astype(np.float32)
    if ink.ndim == 3:
        ink = ink.mean(2)
    ds = WW / ink.shape[1]
    w = int(round(REGION / ds))
    m = (ink > 128).astype(np.float32)
    cs = m.cumsum(0).cumsum(1)
    s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
    c = s / float(w * w)
    c[c < 0.08] = np.inf
    iy, ix = np.unravel_index(int(np.abs(c - 0.30).argmin()), c.shape)
    cy0 = max(0, min(HH // CH - REGION // CH, int(round(iy * ds / CH))))
    cx0 = max(0, min(WW // CH - REGION // CH, int(round(ix * ds / CH))))
    nt = REGION // CH
    log(f"D={D} canvas {HH}x{WW} ds={ds:.1f}; window ink-px ({iy},{ix}) "
        f"chunks ({cy0},{cx0}) {nt}x{nt}")

    stack = np.zeros((DLAY, REGION, REGION), np.uint8)
    got = [0]

    def g(cy, cx):
        try:
            b = get(f"{B}/{SV}0/0/{cy}/{cx}")
            if len(b) == D * CH * CH:
                a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)[:DLAY]
                stack[:, (cy - cy0) * CH:(cy - cy0 + 1) * CH,
                      (cx - cx0) * CH:(cx - cx0 + 1) * CH] = a
                got[0] += 1
        except Exception:
            pass

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda q: g(*q), [(cy0 + j, cx0 + i)
                                      for j in range(nt) for i in range(nt)]))
    log(f"chunks {got[0]}/{nt*nt} in {time.time()-t0:.0f}s")

    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-0",
                                      trust_remote_code=True).eval().cuda()
    H = W = REGION
    Hq, Wq = H // 4, W // 4
    acc = np.zeros((Hq, Wq), np.float32)
    cnt = np.zeros((Hq, Wq), np.float32)
    coords = [(y, x) for y in range(0, H - WINDOW + 1, STRIDE)
              for x in range(0, W - WINDOW + 1, STRIDE)]
    t0 = time.time()
    BATCH = 16
    with torch.no_grad():
        for i in range(0, len(coords), BATCH):
            bc = coords[i:i + BATCH]
            tiles = np.stack([np.clip(stack[:, y:y + WINDOW, x:x + WINDOW]
                                      .astype(np.float32), 0, 200) / 255.0
                              for y, x in bc])
            tt = torch.from_numpy(tiles).unsqueeze(1).cuda()
            # average LOGITS across overlaps, sigmoid once at the end —
            # averaging probabilities flattens confident overlaps
            pr = model(tt).logits[:, 0].cpu().numpy()
            for (y, x), p in zip(bc, pr):
                acc[y // 4:y // 4 + 64, x // 4:x // 4 + 64] += p
                cnt[y // 4:y // 4 + 64, x // 4:x // 4 + 64] += 1
            if i % (BATCH * 20) == 0:
                log(f"  {i+len(bc)}/{len(coords)} tiles "
                    f"{(time.time()-t0)/max(i+len(bc),1)*1000:.0f}ms/tile")
    pred = 1.0 / (1.0 + np.exp(-(acc / np.maximum(cnt, 1))))
    log(f"inference {len(coords)} tiles in {time.time()-t0:.0f}s")

    ink_c = ink[int(cy0 * CH / ds):int(cy0 * CH / ds) + int(H / ds),
                int(cx0 * CH / ds):int(cx0 * CH / ds) + int(W / ds)]
    ink_q = np.array(Image.fromarray(ink_c.astype(np.uint8))
                     .resize((Wq, Hq), Image.BILINEAR))
    tgt = ink_q > 128
    x_ = pred.ravel()
    o = np.argsort(x_)
    rk = np.empty(len(x_)); rk[o] = np.arange(1, len(x_) + 1)
    y_ = tgt.ravel()
    n1, n0 = int(y_.sum()), int((~y_).sum())
    auc = float("nan")
    if n1 > 50 and n0 > 50:
        auc = (rk[y_].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
        auc = max(auc, 1 - auc)
    r = float(np.corrcoef(pred.ravel(), ink_q.ravel())[0, 1])

    def norm(v):
        lo, hi = np.percentile(v, [2, 98])
        return (np.clip((v - lo) / max(hi - lo, 1e-9), 0, 1) * 255).astype(np.uint8)
    gap = np.full((Hq, 6), 255, np.uint8)
    strip = np.concatenate([norm(ink_q), gap, norm(pred)], 1)
    img = Image.fromarray(strip).convert("RGB")
    ImageDraw.Draw(img).text((8, 8), f"published | GPU inference  "
                             f"AUC {auc:.3f} r {r:+.3f}  9.2mm window",
                             fill=(255, 200, 40))
    img.save(os.path.join(OUT, "wide.png"))
    np.save(os.path.join(OUT, "pred.npy"), pred)
    Image.fromarray(norm(pred)).save(os.path.join(OUT, "pred.png"))
    json.dump(dict(auc=auc, r=r, tiles=len(coords), chunks=got[0],
                   window=[int(cy0 * CH), int(cx0 * CH), REGION]),
              open(os.path.join(OUT, "done.json"), "w"))
    log(f"DONE auc={auc:.3f} r={r:+.3f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log(f"FAILED: {e}")
