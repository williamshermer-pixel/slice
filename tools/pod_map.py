"""POD MAP — fixed-renderer margin mapping, parallelisable by segment subset.
Recipe proven on ground truth 2026-07-29 (AUC 0.944): iteration-5 model,
depth band z27..z89, Gaussian-weighted logit blending, stride 64.
SEGS injected by launcher; writes map_<i>.npy + meta per segment.
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEGS = __SEGS__
TAG = "__TAG__"
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, DLAY, WINDOW, STRIDE, Z0 = 4096, 62, 256, 64, 27
_gy, _gx = np.mgrid[0:64, 0:64]
GW = np.exp(-(((_gy-31.5)/18)**2 + ((_gx-31.5)/18)**2)/2).astype(np.float32)


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=120):
    return urllib.request.urlopen(u, timeout=t).read()


def main():
    from PIL import Image
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-5",
                                      trust_remote_code=True).eval().cuda()
    for i, t in enumerate(SEGS):
        try:
            za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
            D, HH, WW = za["shape"]
            if D < Z0 + DLAY:
                log(f"[{i}] stack too shallow ({D})"); continue
            ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
            if ink.ndim == 3:
                ink = ink.mean(2)
            ds = WW / ink.shape[1]
            w = int(round(REGION / ds))
            if ink.shape[0] <= w or ink.shape[1] <= w:
                log(f"[{i}] segment smaller than window"); continue
            m = (ink > 128).astype(np.float32)
            cs = m.cumsum(0).cumsum(1)
            s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
            c = s / float(w*w)
            c[c < 0.02] = np.inf
            iy, ix = np.unravel_index(int(np.abs(c - 0.10).argmin()), c.shape)
            if not np.isfinite(c[iy, ix]):
                log(f"[{i}] no margin window"); continue
            cy0 = max(0, min(HH//CH - REGION//CH, int(round(iy*ds/CH))))
            cx0 = max(0, min(WW//CH - REGION//CH, int(round(ix*ds/CH))))
            nt = REGION // CH
            stack = np.zeros((DLAY, REGION, REGION), np.uint8)
            got = [0]
            def g(cy, cx):
                try:
                    b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
                    if len(b) == D*CH*CH:
                        a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)[Z0:Z0+DLAY]
                        stack[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
                        got[0] += 1
                except Exception:
                    pass
            with cf.ThreadPoolExecutor(max_workers=32) as ex:
                list(ex.map(lambda q: g(*q), [(cy0+j, cx0+k) for j in range(nt) for k in range(nt)]))
            if got[0] < nt*nt*0.4:
                log(f"[{i}] sparse ({got[0]}/{nt*nt})"); continue
            Hq = REGION // 4
            acc = np.zeros((Hq, Hq), np.float32)
            cnt = np.zeros((Hq, Hq), np.float32) + 1e-6
            coords = [(y, x) for y in range(0, REGION-WINDOW+1, STRIDE)
                      for x in range(0, REGION-WINDOW+1, STRIDE)]
            t0 = time.time()
            with torch.no_grad():
                for b0 in range(0, len(coords), 16):
                    bc = coords[b0:b0+16]
                    tiles = np.stack([np.clip(stack[:, y:y+WINDOW, x:x+WINDOW]
                                              .astype(np.float32), 0, 200)/255.0
                                      for y, x in bc])
                    tt = torch.from_numpy(tiles).unsqueeze(1).cuda()
                    pr = model(tt).logits[:, 0].float().cpu().numpy()
                    for (y, x), p in zip(bc, pr):
                        acc[y//4:y//4+64, x//4:x//4+64] += p*GW
                        cnt[y//4:y//4+64, x//4:x//4+64] += GW
            pred = 1.0/(1.0+np.exp(-(acc/cnt)))
            np.save(os.path.join(OUT, f"map_{TAG}_{i}.npy"), pred.astype(np.float32))
            json.dump(dict(seg=t["seg"], window=[int(cy0*CH), int(cx0*CH), REGION], z=Z0),
                      open(os.path.join(OUT, f"meta_{TAG}_{i}.json"), "w"))
            log(f"[{i}] {t['seg'].split('/')[-2][:24]} mapped "
                f"({got[0]} chunks, {time.time()-t0:.0f}s infer)")
        except Exception as e:
            log(f"[{i}] failed: {e}")
    json.dump(dict(done=True, n=len(SEGS), tag=TAG),
              open(os.path.join(OUT, "done.json"), "w"))
    log("MAP SHARD DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
