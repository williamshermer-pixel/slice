"""POD DEPTH PROFILE — true 3D ink labels for ScrollPrize/villa #192.

#192 asks for ink labels "in true 3d rather than a single image projected
across multiple layers". Our first labels WERE that projection (one 2D map
written into every layer of the measured band) — this replaces them.

Method: the model consumes a fixed 62-layer stack, so depth information is
recovered by SLIDING that window through the surface volume. For each offset
z_k the model returns a full 2D ink probability; stacking those gives every
pixel a measured DEPTH RESPONSE PROFILE p(z_k). Ink is then attributed to the
depth where that pixel's response actually peaks, not smeared across the band.

Honest limits, carried into the label's .zattrs:
  - effective depth resolution is the offset STEP (not one layer): the reading
    window is 62 layers wide, so profiles are smoothed at that scale;
  - a pixel with a flat profile gets no depth attribution (code 3) rather than
    a guessed one.

Emits per window: prof_<tag>.npy = (K, 1024, 1024) float32 profiles, plus the
offsets used. The laptop assembles the zarr labels from these.
SEGS/TAG/OFFSETS injected by the launcher.
"""
import io, json, os, threading, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEGS = __SEGS__
TAG = "__TAG__"
OFFSETS = __OFFSETS__          # sliding 62-layer window starts
AIMS = __AIMS__
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, DLAY, WINDOW, STRIDE = 4096, 62, 256, 64
_gy, _gx = np.mgrid[0:64, 0:64]
GW = np.exp(-(((_gy-31.5)/18)**2 + ((_gx-31.5)/18)**2)/2).astype(np.float32)


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=120):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=t).read()


def serve():
    import http.server

    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    os.chdir("/workspace")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()


def pick_windows(ink, ds, HH, WW):
    w = int(round(REGION / ds))
    if ink.shape[0] <= w or ink.shape[1] <= w:
        return []
    m = (ink > 128).astype(np.float32)
    cs = m.cumsum(0).cumsum(1)
    s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
    c = s / float(w * w)
    c[c < 0.02] = np.inf
    outs, seen = [], set()
    for aim in AIMS:
        iy, ix = np.unravel_index(int(np.abs(c - aim).argmin()), c.shape)
        if not np.isfinite(c[iy, ix]):
            continue
        cy0 = max(0, min(HH // CH - REGION // CH, int(round(iy * ds / CH))))
        cx0 = max(0, min(WW // CH - REGION // CH, int(round(ix * ds / CH))))
        if (cy0, cx0) in seen:
            continue
        seen.add((cy0, cx0))
        outs.append((aim, cy0, cx0, float(c[iy, ix])))
    return outs


def infer(model, torch, stack):
    """One 2D probability map from a 62-layer stack."""
    Hq = REGION // 4
    acc = np.zeros((Hq, Hq), np.float32)
    cnt = np.zeros((Hq, Hq), np.float32) + 1e-6
    coords = [(y, x) for y in range(0, REGION - WINDOW + 1, STRIDE)
              for x in range(0, REGION - WINDOW + 1, STRIDE)]
    with torch.no_grad():
        for b0 in range(0, len(coords), 16):
            bc = coords[b0:b0 + 16]
            tiles = np.stack([np.clip(stack[:, y:y+WINDOW, x:x+WINDOW]
                                      .astype(np.float32), 0, 200) / 255.0
                              for y, x in bc])
            tt = torch.from_numpy(tiles).unsqueeze(1).cuda()
            pr = model(tt).logits[:, 0].float().cpu().numpy()
            for (y, x), p in zip(bc, pr):
                acc[y//4:y//4+64, x//4:x//4+64] += p * GW
                cnt[y//4:y//4+64, x//4:x//4+64] += GW
    return 1.0 / (1.0 + np.exp(-(acc / cnt)))


def main():
    threading.Thread(target=serve, daemon=True).start()
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-5",
                                      trust_remote_code=True).eval().cuda()
    log(f"depth profiling at offsets {OFFSETS}")

    for si, t in enumerate(SEGS):
        try:
            za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
            D, HH, WW = za["shape"]
            usable = [z for z in OFFSETS if z + DLAY <= D]
            if len(usable) < 3:
                log(f"[{si}] stack {D} too shallow for a profile")
                continue
            a = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))
                         ).astype(np.float32)
            if a.ndim == 3:
                a = a.mean(2)
            wins = pick_windows(a, WW / a.shape[1], HH, WW)
            for wi, (aim, cy0, cx0, cov) in enumerate(wins):
                nt = REGION // CH
                # fetch the FULL depth once — chunks carry every layer anyway
                full = np.zeros((D, REGION, REGION), np.uint8)
                got = [0]

                def g(cy, cx):
                    try:
                        b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
                        if len(b) == D * CH * CH:
                            full[:, (cy-cy0)*CH:(cy-cy0+1)*CH,
                                 (cx-cx0)*CH:(cx-cx0+1)*CH] = \
                                np.frombuffer(b, np.uint8).reshape(D, CH, CH)
                            got[0] += 1
                    except Exception:
                        pass
                with cf.ThreadPoolExecutor(max_workers=32) as ex:
                    list(ex.map(lambda q: g(*q),
                                [(cy0+j, cx0+k) for j in range(nt)
                                 for k in range(nt)]))
                if got[0] < nt * nt * 0.4:
                    log(f"[{si}.{wi}] sparse ({got[0]})")
                    continue
                t0 = time.time()
                prof = np.stack([infer(model, torch, full[z:z+DLAY])
                                 for z in usable])          # (K,1024,1024)
                np.save(os.path.join(OUT, f"prof_{TAG}_{si}_{wi}.npy"),
                        prof.astype(np.float32))
                tex = full[27:89].mean(0).reshape(1024, 4, 1024, 4).mean((1, 3))
                np.save(os.path.join(OUT, f"tex_{TAG}_{si}_{wi}.npy"),
                        tex.astype(np.uint8))
                json.dump(dict(seg=t["seg"], aim=aim, cov=cov,
                               offsets=usable, depth_window=DLAY, stack_depth=D,
                               window=[int(cy0*CH), int(cx0*CH), REGION]),
                          open(os.path.join(OUT,
                                            f"meta_{TAG}_{si}_{wi}.json"), "w"))
                log(f"[{si}.{wi}] profiled {len(usable)} offsets "
                    f"({time.time()-t0:.0f}s)")
                del full
        except Exception as e:
            log(f"[{si}] failed: {e}")
    json.dump(dict(done=True, tag=TAG), open(os.path.join(OUT, "done.json"), "w"))
    log("DEPTH PROFILE DONE")
    time.sleep(86400)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
        time.sleep(86400)
