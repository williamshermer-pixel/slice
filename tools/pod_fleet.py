"""POD FLEET — map the lost book's margins at scale. One pod pass over many
PHerc0139 segments: margin-aimed window each, raw sigmoid map saved per
segment. Local sweep (scribe's measured hand: 1.1 mm letters, 4.57 mm
pitch) grades them after download. SEGS injected by launcher.
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEGS = __SEGS__
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, DLAY, WINDOW, STRIDE = 4096, 62, 256, 128


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=90):
    return urllib.request.urlopen(u, timeout=t).read()


def run_seg(i, t, model, torch):
    from PIL import Image
    za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
    D, HH, WW = za["shape"]
    ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
    if ink.ndim == 3:
        ink = ink.mean(2)
    ds = WW / ink.shape[1]
    w = int(round(REGION / ds))
    if ink.shape[0] <= w or ink.shape[1] <= w:
        log(f"[{i}] segment too small"); return
    m = (ink > 128).astype(np.float32)
    cs = m.cumsum(0).cumsum(1)
    s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
    c = s / float(w * w)
    c[c < 0.02] = np.inf                      # need SOME nearby text
    iy, ix = np.unravel_index(int(np.abs(c - 0.10).argmin()), c.shape)
    if not np.isfinite(c[iy, ix]):
        log(f"[{i}] no margin window"); return
    cy0 = max(0, min(HH // CH - REGION // CH, int(round(iy * ds / CH))))
    cx0 = max(0, min(WW // CH - REGION // CH, int(round(ix * ds / CH))))
    nt = REGION // CH
    stack = np.zeros((DLAY, REGION, REGION), np.uint8)
    got = [0]

    def g(cy, cx):
        try:
            b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
            if len(b) == D * CH * CH:
                a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)[:DLAY]
                stack[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
                got[0] += 1
        except Exception:
            pass
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda q: g(*q), [(cy0+j, cx0+i2) for j in range(nt) for i2 in range(nt)]))
    if got[0] < nt * nt * 0.4:
        log(f"[{i}] sparse fetch {got[0]}/{nt*nt}, skipping"); return

    H = W = REGION
    Hq, Wq = H // 4, W // 4
    acc = np.zeros((Hq, Wq), np.float32)
    cnt = np.zeros((Hq, Wq), np.float32)
    coords = [(y, x) for y in range(0, H-WINDOW+1, STRIDE)
              for x in range(0, W-WINDOW+1, STRIDE)]
    with torch.no_grad():
        for b0 in range(0, len(coords), 16):
            bc = coords[b0:b0+16]
            tiles = np.stack([np.clip(stack[:, y:y+WINDOW, x:x+WINDOW]
                                      .astype(np.float32), 0, 200) / 255.0
                              for y, x in bc])
            tt = __import__("torch").from_numpy(tiles).unsqueeze(1).cuda()
            pr = model(tt).logits[:, 0].cpu().numpy()
            for (y, x), p in zip(bc, pr):
                acc[y//4:y//4+64, x//4:x//4+64] += p
                cnt[y//4:y//4+64, x//4:x//4+64] += 1
    pred = 1.0 / (1.0 + np.exp(-(acc / np.maximum(cnt, 1))))
    np.save(os.path.join(OUT, f"pred_{i}.npy"), pred.astype(np.float32))
    json.dump(dict(seg=t["seg"], window=[int(cy0*CH), int(cx0*CH), REGION],
                   chunks=got[0]),
              open(os.path.join(OUT, f"meta_{i}.json"), "w"))
    log(f"[{i}] {t['seg'].split('/')[-2][:24]} mapped ({got[0]} chunks)")


def main():
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-0",
                                      trust_remote_code=True).eval().cuda()
    t0 = time.time()
    for i, t in enumerate(SEGS):
        try:
            run_seg(i, t, model, torch)
        except Exception as e:
            log(f"[{i}] failed: {e}")
    json.dump(dict(done=True, n=len(SEGS), secs=round(time.time()-t0)),
              open(os.path.join(OUT, "done.json"), "w"))
    log("FLEET DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
