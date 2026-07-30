"""Production-spec renderer: iter-5, z27 band, PROBABILITY-space blending
(sigmoid before weighting, per all three production repos), 4-way TTA
(orig/hflip/vflip/rot90, mean of probs), Hann window sum-normalized,
Grand Prize max-stretch on save. Two targets injected."""
import io, os, json, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEGS = [{"seg": "PHercParis4/segments/20230702185753/", "sv": "PHercParis4/segments/20230702185753/surface-volumes/1.129um-0.23m-78keV-volume-20260608103018-L1.zarr/", "ink": "PHercParis4/segments/20230702185753/ink-detection/downsampled/PHercParis4-20230702185753-1.129um-0.23m-78keV-volume-20260608103018-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg", "aim": 0.4}, {"seg": "PHerc0139/segments/20250223000000-w059_2025022312/", "sv": "PHerc0139/segments/20250223000000-w059_2025022312/surface-volumes/1.129um-0.22m-59keV-volume-20260413113053-L1.zarr/", "ink": "PHerc0139/segments/20250223000000-w059_2025022312/ink-detection/downsampled/PHerc0139-20250223000000-1.129um-0.22m-59keV-volume-20260413113053-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg", "aim": 0.1}]
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, DLAY, WINDOW, STRIDE, Z0 = 4096, 62, 256, 64, 27
h = np.hanning(64).astype(np.float32)
HANN = np.outer(h, h); HANN /= HANN.sum()

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
        za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
        D, HH, WW = za["shape"]
        ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
        if ink.ndim == 3: ink = ink.mean(2)
        ds = WW/ink.shape[1]; w = int(round(REGION/ds))
        m = (ink > 128).astype(np.float32)
        cs = m.cumsum(0).cumsum(1)
        s = cs[w:, w:]-cs[:-w, w:]-cs[w:, :-w]+cs[:-w, :-w]
        c = s/float(w*w); c[c < 0.02] = np.inf
        iy, ix = np.unravel_index(int(np.abs(c - t["aim"]).argmin()), c.shape)
        cy0 = max(0, min(HH//CH-REGION//CH, int(round(iy*ds/CH))))
        cx0 = max(0, min(WW//CH-REGION//CH, int(round(ix*ds/CH))))
        nt = REGION//CH
        stack = np.zeros((DLAY, REGION, REGION), np.uint8)
        got = [0]
        def g(cy, cx):
            try:
                b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
                if len(b) == D*CH*CH:
                    stack[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = \
                        np.frombuffer(b, np.uint8).reshape(D, CH, CH)[Z0:Z0+DLAY]
                    got[0] += 1
            except Exception: pass
        with cf.ThreadPoolExecutor(max_workers=32) as ex:
            list(ex.map(lambda q: g(*q), [(cy0+j, cx0+k) for j in range(nt) for k in range(nt)]))
        log(f"[{i}] fetched {got[0]}/{nt*nt}")
        Hq = REGION//4
        acc = np.zeros((Hq, Hq), np.float32); cnt = np.zeros((Hq, Hq), np.float32)+1e-9
        coords = [(y, x) for y in range(0, REGION-WINDOW+1, STRIDE)
                  for x in range(0, REGION-WINDOW+1, STRIDE)]
        t0 = time.time()
        with torch.no_grad():
            for b0 in range(0, len(coords), 8):
                bc = coords[b0:b0+8]
                base = np.stack([np.clip(stack[:, y:y+WINDOW, x:x+WINDOW]
                                         .astype(np.float32), 0, 200)/255.0 for y, x in bc])
                views = [base, base[:, :, :, ::-1].copy(), base[:, :, ::-1, :].copy(),
                         np.rot90(base, 1, axes=(2, 3)).copy()]
                probs = []
                for vi, v in enumerate(views):
                    tt = torch.from_numpy(v).unsqueeze(1).cuda()
                    p = torch.sigmoid(model(tt).logits)[:, 0].float().cpu().numpy()
                    if vi == 1: p = p[:, :, ::-1]
                    elif vi == 2: p = p[:, ::-1, :]
                    elif vi == 3: p = np.rot90(p, -1, axes=(1, 2))
                    probs.append(p)
                pm = np.mean(probs, axis=0)
                for (y, x), p in zip(bc, pm):
                    acc[y//4:y//4+64, x//4:x//4+64] += p*HANN
                    cnt[y//4:y//4+64, x//4:x//4+64] += HANN
        pred = acc/cnt
        gp = np.clip(np.nan_to_num(pred), 0, 1); gp = gp/max(gp.max(), 1e-9)
        np.save(os.path.join(OUT, f"final_{i}.npy"), pred.astype(np.float32))
        Image.fromarray((gp*255).astype(np.uint8)).save(os.path.join(OUT, f"final_{i}.png"))
        json.dump(dict(seg=t["seg"], window=[int(cy0*CH), int(cx0*CH), REGION]),
                  open(os.path.join(OUT, f"finalmeta_{i}.json"), "w"))
        log(f"[{i}] {t['seg'].split('/')[-2][:24]} done ({time.time()-t0:.0f}s)")
    json.dump(dict(done=True), open(os.path.join(OUT, "done.json"), "w"))
    log("DONE")

if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
