"""POD WIDE — map a CONTIGUOUS GRID, so a human can see whether it is writing.

Every search in this project scored a single 4096-px window: 9.25 mm, about
eleven letters, two text lines. No statistic and no pair of eyes can judge
writing through that. Every real discovery in this field came from assembling
a large map and looking at it.

So: same model, same measured depth band, same recipe — but a G x G grid of
adjacent windows, stitched into one continuous map spanning ~46 mm. That is a
whole text column, 8-12 lines, ~28 letters across. Statistics then only rank
where to look; the human decides.

SEG / CY0 / CX0 / G injected by the launcher.
"""
import io, json, os, threading, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEG = __SEG__
CY0, CX0, G = __CY0__, __CX0__, __G__
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, DLAY, WINDOW, STRIDE, Z0 = 4096, 62, 256, 64, 27
NT = REGION // CH                      # 32 chunks per window edge
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


def main():
    threading.Thread(target=serve, daemon=True).start()
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-5",
                                      trust_remote_code=True).eval().cuda()
    za = json.loads(get(f"{B}/{SEG['sv']}0/.zarray").decode())
    D, HH, WW = za["shape"]
    log(f"volume {D}x{HH}x{WW} · grid {G}x{G} from chunk ({CY0},{CX0}) "
        f"= {G*REGION*2.258/1000:.1f} mm across")

    for i in range(G):
        for j in range(G):
            cy0, cx0 = CY0 + i * NT, CX0 + j * NT
            if (cy0 + NT) * CH > HH or (cx0 + NT) * CH > WW:
                log(f"[{i},{j}] outside volume"); continue
            stack = np.zeros((DLAY, REGION, REGION), np.uint8)
            got = [0]

            def g(cy, cx):
                try:
                    b = get(f"{B}/{SEG['sv']}0/0/{cy}/{cx}")
                    if len(b) == D * CH * CH:
                        a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)[Z0:Z0+DLAY]
                        stack[:, (cy-cy0)*CH:(cy-cy0+1)*CH,
                              (cx-cx0)*CH:(cx-cx0+1)*CH] = a
                        got[0] += 1
                except Exception:
                    pass
            with cf.ThreadPoolExecutor(max_workers=32) as ex:
                list(ex.map(lambda q: g(*q),
                            [(cy0+a, cx0+b) for a in range(NT) for b in range(NT)]))
            if got[0] < NT * NT * 0.3:
                log(f"[{i},{j}] sparse ({got[0]}/{NT*NT})"); continue
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
            np.save(os.path.join(OUT, f"cell_{i}_{j}.npy"), pred.astype(np.float32))
            tex = stack.mean(0).reshape(Hq, 4, Hq, 4).mean((1, 3)).astype(np.uint8)
            np.save(os.path.join(OUT, f"tex_{i}_{j}.npy"), tex)
            log(f"[{i},{j}] mapped ({got[0]} chunks, {time.time()-t0:.0f}s)")
            del stack
    json.dump(dict(done=True, seg=SEG["seg"], grid=G, origin=[CY0, CX0],
                   chunk=CH, region=REGION),
              open(os.path.join(OUT, "done.json"), "w"))
    log("WIDE FIELD DONE")
    time.sleep(86400)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
        time.sleep(86400)
