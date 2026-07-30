"""POD LOSTBOOK — tuned-eyes mapping of PHerc0139 for the differential hunt.
Loads the honest bootstrap weights (held-out 0.850->0.944) onto iter-5 and
maps up to 3 aimed windows per segment — text band 0.30 / edge 0.12 /
margin 0.04 — with the proven recipe (z27..z89, gaussian logit blend,
stride 64). Saves raw sigmoid maps + depth-mean texture per window for the
laptop differential and gallery. Runs its own :8000 server for weight
delivery (PUT parts) and result harvest. SEGS/WSRC/TAG injected by launcher.
"""
import hashlib, io, json, os, threading, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEGS = __SEGS__
WSRC = "__WSRC__"          # "local": parts arrive by PUT; else hub base URL
TAG = "__TAG__"
AIMS = [0.30, 0.12, 0.04]
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
WPT = "/workspace/tuned.pt"
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


def serve():
    import http.server

    class H(http.server.SimpleHTTPRequestHandler):
        def do_PUT(self):
            n = int(self.headers["Content-Length"])
            p = os.path.join("/workspace", os.path.basename(self.path))
            with open(p, "wb") as f:
                r = n
                while r > 0:
                    b = self.rfile.read(min(r, 1 << 20))
                    if not b:
                        break
                    f.write(b)
                    r -= len(b)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    os.chdir("/workspace")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()


def weights_ready():
    """Assemble /workspace/tuned.pt from parts, local or hub-fetched."""
    def manifest():
        if WSRC == "local":
            p = "/workspace/tuned.manifest"
            return json.loads(open(p).read()) if os.path.exists(p) else None
        try:
            return json.loads(get(WSRC + "/tuned.manifest", t=30).decode())
        except Exception:
            return None

    mf = None
    for k in range(360):
        mf = manifest()
        if mf:
            break
        if k % 8 == 0:
            log(f"waiting for weight manifest ({k})")
        time.sleep(10)
    if not mf:
        raise RuntimeError("no weight manifest after 60 min")
    for j in range(mf["parts"]):
        p = f"/workspace/tuned.part{j}"
        for a in range(30):
            if os.path.exists(p) and os.path.getsize(p) == mf["sizes"][j]:
                break
            if WSRC != "local":
                try:
                    open(p, "wb").write(get(f"{WSRC}/tuned.part{j}", t=300))
                except Exception as e:
                    log(f"part{j} attempt {a}: {e}")
                    time.sleep(10)
            else:
                time.sleep(10)
        if not (os.path.exists(p) and os.path.getsize(p) == mf["sizes"][j]):
            raise RuntimeError(f"part{j} never arrived")
    h = hashlib.md5()
    with open(WPT, "wb") as f:
        for j in range(mf["parts"]):
            b = open(f"/workspace/tuned.part{j}", "rb").read()
            h.update(b)
            f.write(b)
    if h.hexdigest() != mf["md5"]:
        raise RuntimeError("weights md5 mismatch")
    log(f"weights assembled ({os.path.getsize(WPT)} bytes, md5 ok)")


def pick_windows(ink, ds, HH, WW):
    """Aimed windows over the coverage field, deduped by chunk origin."""
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


def run_window(model, torch, t, D, wi, aim, cy0, cx0, cov, si):
    nt = REGION // CH
    stack = np.zeros((DLAY, REGION, REGION), np.uint8)
    got = [0]

    def g(cy, cx):
        try:
            b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
            if len(b) == D * CH * CH:
                a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)[Z0:Z0 + DLAY]
                stack[:, (cy - cy0) * CH:(cy - cy0 + 1) * CH,
                      (cx - cx0) * CH:(cx - cx0 + 1) * CH] = a
                got[0] += 1
        except Exception:
            pass
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda q: g(*q),
                    [(cy0 + j, cx0 + k) for j in range(nt) for k in range(nt)]))
    if got[0] < nt * nt * 0.4:
        log(f"[{si}.{wi}] sparse ({got[0]}/{nt*nt})")
        return
    Hq = REGION // 4
    acc = np.zeros((Hq, Hq), np.float32)
    cnt = np.zeros((Hq, Hq), np.float32) + 1e-6
    coords = [(y, x) for y in range(0, REGION - WINDOW + 1, STRIDE)
              for x in range(0, REGION - WINDOW + 1, STRIDE)]
    t0 = time.time()
    with torch.no_grad():
        for b0 in range(0, len(coords), 16):
            bc = coords[b0:b0 + 16]
            tiles = np.stack([np.clip(stack[:, y:y + WINDOW, x:x + WINDOW]
                                      .astype(np.float32), 0, 200) / 255.0
                              for y, x in bc])
            tt = torch.from_numpy(tiles).unsqueeze(1).cuda()
            pr = model(tt).logits[:, 0].float().cpu().numpy()
            for (y, x), p in zip(bc, pr):
                acc[y // 4:y // 4 + 64, x // 4:x // 4 + 64] += p * GW
                cnt[y // 4:y // 4 + 64, x // 4:x // 4 + 64] += GW
    pred = 1.0 / (1.0 + np.exp(-(acc / cnt)))
    tex = stack.mean(0).reshape(Hq, 4, Hq, 4).mean((1, 3)).astype(np.uint8)
    np.save(os.path.join(OUT, f"map_{TAG}_{si}_{wi}.npy"), pred.astype(np.float32))
    np.save(os.path.join(OUT, f"tex_{TAG}_{si}_{wi}.npy"), tex)
    json.dump(dict(seg=t["seg"], aim=aim, cov=cov, z=Z0,
                   window=[int(cy0 * CH), int(cx0 * CH), REGION]),
              open(os.path.join(OUT, f"meta_{TAG}_{si}_{wi}.json"), "w"))
    log(f"[{si}.{wi}] aim {aim:.2f} cov {cov:.2f} mapped "
        f"({got[0]} chunks, {time.time()-t0:.0f}s)")


def main():
    threading.Thread(target=serve, daemon=True).start()
    weights_ready()
    from PIL import Image
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-5",
                                      trust_remote_code=True)
    sd = torch.load(WPT, map_location="cpu")
    model.load_state_dict(sd)
    model.eval().cuda()
    log("tuned model loaded on iter-5")
    for si, t in enumerate(SEGS):
        try:
            za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
            D, HH, WW = za["shape"]
            if D < Z0 + DLAY:
                log(f"[{si}] stack too shallow ({D})")
                continue
            ink = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))
                           ).astype(np.float32)
            if ink.ndim == 3:
                ink = ink.mean(2)
            wins = pick_windows(ink, WW / ink.shape[1], HH, WW)
            if not wins:
                log(f"[{si}] no windows")
                continue
            for wi, (aim, cy0, cx0, cov) in enumerate(wins):
                run_window(model, torch, t, D, wi, aim, cy0, cx0, cov, si)
        except Exception as e:
            log(f"[{si}] failed: {e}")
    json.dump(dict(done=True, n=len(SEGS), tag=TAG),
              open(os.path.join(OUT, "done.json"), "w"))
    log("LOSTBOOK SHARD DONE")
    time.sleep(86400)   # keep the server alive for harvest; launcher terminates


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
        time.sleep(86400)   # keep the server alive so error.txt is fetchable
