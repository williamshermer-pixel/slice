"""POD TRAIN HONEST — per-scribe adaptation with the PROVEN recipe.

The 2023 Scroll-1 playbook, run correctly: fine-tune iter-5 on THIS scroll's
called text using the verified renderer settings (depth band z27..z89,
gaussian-weighted logit blending) — the earlier pod_train2 used iteration-0
and the wrong depth band, so its +0.112 gain UNDERSTATES what this recipe
buys. Validates on a held-out segment it never saw (A/B, same windows), then
remaps every segment in SEGS_MAP with tuned eyes in pod_lostbook's exact
output format, so the laptop chain (floor/detector/control/hunt) runs
unchanged. Serves everything on :8000. SEGS/SEGS_MAP/TAG injected.
"""
import io, json, os, threading, time, urllib.request
import concurrent.futures as cf
import numpy as np

SEGS = __SEGS__            # first N-1 train, last is HELD OUT
SEGS_MAP = __SEGS_MAP__
TAG = "__TAG__"
AIMS = [0.35, 0.20, 0.08]
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, DLAY, WINDOW, STRIDE, Z0 = 4096, 62, 256, 64, 27
STEPS, BATCH, LR = 400, 4, 3e-5
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


def load_ink(t):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    a = np.array(Image.open(io.BytesIO(get(f"{B}/{t['ink']}")))).astype(np.float32)
    return a.mean(2) if a.ndim == 3 else a


def fetch_stack(t, D, cy0, cx0):
    nt = REGION // CH
    stack = np.zeros((DLAY, REGION, REGION), np.uint8)
    got = [0]

    def g(cy, cx):
        try:
            b = get(f"{B}/{t['sv']}0/0/{cy}/{cx}")
            if len(b) == D * CH * CH:
                a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)[Z0:Z0 + DLAY]
                stack[:, (cy-cy0)*CH:(cy-cy0+1)*CH,
                      (cx-cx0)*CH:(cx-cx0+1)*CH] = a
                got[0] += 1
        except Exception:
            pass
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda q: g(*q),
                    [(cy0+j, cx0+k) for j in range(nt) for k in range(nt)]))
    return stack, got[0]


def aimed_origin(ink, ds, HH, WW, aim):
    w = int(round(REGION / ds))
    if ink.shape[0] <= w or ink.shape[1] <= w:
        return None
    m = (ink > 128).astype(np.float32)
    cs = m.cumsum(0).cumsum(1)
    s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
    c = s / float(w * w)
    c[c < 0.02] = np.inf
    iy, ix = np.unravel_index(int(np.abs(c - aim).argmin()), c.shape)
    if not np.isfinite(c[iy, ix]):
        return None
    cy0 = max(0, min(HH // CH - REGION // CH, int(round(iy * ds / CH))))
    cx0 = max(0, min(WW // CH - REGION // CH, int(round(ix * ds / CH))))
    return cy0, cx0, float(c[iy, ix])


def fetch_region(t, aim):
    """Stack + aligned label for one aimed window (train/validate path)."""
    za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
    D, HH, WW = za["shape"]
    if D < Z0 + DLAY:
        return None
    ink = load_ink(t)
    ds = WW / ink.shape[1]
    o = aimed_origin(ink, ds, HH, WW, aim)
    if o is None:
        return None
    cy0, cx0, cov = o
    stack, got = fetch_stack(t, D, cy0, cx0)
    if got < (REGION // CH) ** 2 * 0.4:
        return None
    from PIL import Image
    y0i, x0i = int(cy0 * CH / ds), int(cx0 * CH / ds)
    w = int(round(REGION / ds))
    lab = ink[y0i:y0i + w, x0i:x0i + w]
    lab = np.array(Image.fromarray((lab > 128).astype(np.uint8) * 255)
                   .resize((REGION, REGION), Image.NEAREST)) > 127
    return stack, lab


def infer_map(model, torch, stack, stride):
    Hq = REGION // 4
    acc = np.zeros((Hq, Hq), np.float32)
    cnt = np.zeros((Hq, Hq), np.float32) + 1e-6
    coords = [(y, x) for y in range(0, REGION - WINDOW + 1, stride)
              for x in range(0, REGION - WINDOW + 1, stride)]
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


def auc(pred, lab4):
    x, y = pred.ravel(), lab4.ravel()
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 < 100 or n0 < 100:
        return float("nan")
    o = np.argsort(x)
    rk = np.empty(len(x)); rk[o] = np.arange(1, len(x) + 1)
    a = (rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    return float(max(a, 1 - a))


def main():
    threading.Thread(target=serve, daemon=True).start()
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    import torch
    from transformers import AutoModel
    torch.manual_seed(7)
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-5",
                                      trust_remote_code=True).cuda()

    log("fetching training regions (this scribe's called text, z27 band)")
    train = []
    for t in SEGS[:-1]:
        r = fetch_region(t, 0.35)
        if r:
            train.append(r)
            log(f"  train {t['seg'].split('/')[-2][:22]} cov {r[1].mean():.2f}")
    hold = fetch_region(SEGS[-1], 0.35)
    if len(train) < 2 or hold is None:
        log("not enough data")
        return
    hs, hl = hold
    hl4 = np.array(Image.fromarray(hl.astype(np.uint8) * 255)
                   .resize((REGION//4, REGION//4), Image.BILINEAR)) > 127

    model.eval()
    base_auc = auc(infer_map(model, torch, hs, 128), hl4)
    log(f"BASELINE held-out AUC {base_auc:.3f}")

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(7)
    model.train()
    t0 = time.time()
    for step in range(1, STEPS + 1):
        xs, ys = [], []
        for _ in range(BATCH):
            st, lb = train[rng.integers(len(train))]
            for _ in range(20):
                y0 = int(rng.integers(0, REGION - WINDOW))
                x0 = int(rng.integers(0, REGION - WINDOW))
                l = lb[y0:y0+WINDOW, x0:x0+WINDOW]
                if 0.02 < l.mean() < 0.9:
                    break
            xs.append(np.clip(st[:, y0:y0+WINDOW, x0:x0+WINDOW]
                              .astype(np.float32), 0, 200) / 255.0)
            ys.append(np.array(Image.fromarray(l.astype(np.uint8) * 255)
                               .resize((64, 64), Image.BILINEAR)) / 255.0)
        tt = torch.from_numpy(np.stack(xs)).unsqueeze(1).cuda()
        yy = torch.from_numpy(np.stack(ys).astype(np.float32)).unsqueeze(1).cuda()
        loss = bce(model(tt).logits, yy)
        loss.backward()
        opt.step(); opt.zero_grad()
        if step % 50 == 0:
            log(f"  step {step}/{STEPS} loss {loss.item():.4f} "
                f"{(time.time()-t0)/step:.1f}s/step")

    model.eval()
    tuned_auc = auc(infer_map(model, torch, hs, 128), hl4)
    log(f"TUNED held-out AUC {tuned_auc:.3f} (baseline {base_auc:.3f}, "
        f"delta {tuned_auc-base_auc:+.3f})")
    torch.save(model.state_dict(), os.path.join(OUT, "tuned.pt"))
    json.dump(dict(base_auc=base_auc, tuned_auc=tuned_auc,
                   delta=tuned_auc - base_auc),
              open(os.path.join(OUT, "ab.json"), "w"))

    log(f"remapping {len(SEGS_MAP)} segments with tuned eyes")
    for si, t in enumerate(SEGS_MAP):
        try:
            za = json.loads(get(f"{B}/{t['sv']}0/.zarray").decode())
            D, HH, WW = za["shape"]
            if D < Z0 + DLAY:
                log(f"[{si}] shallow ({D})")
                continue
            ink = load_ink(t)
            ds = WW / ink.shape[1]
            seen = set()
            for wi, aim in enumerate(AIMS):
                o = aimed_origin(ink, ds, HH, WW, aim)
                if o is None or (o[0], o[1]) in seen:
                    continue
                seen.add((o[0], o[1]))
                cy0, cx0, cov = o
                stack, got = fetch_stack(t, D, cy0, cx0)
                if got < (REGION // CH) ** 2 * 0.4:
                    log(f"[{si}.{wi}] sparse ({got})")
                    continue
                pred = infer_map(model, torch, stack, STRIDE)
                Hq = REGION // 4
                tex = stack.mean(0).reshape(Hq, 4, Hq, 4).mean((1, 3)).astype(np.uint8)
                np.save(os.path.join(OUT, f"map_{TAG}_{si}_{wi}.npy"),
                        pred.astype(np.float32))
                np.save(os.path.join(OUT, f"tex_{TAG}_{si}_{wi}.npy"), tex)
                json.dump(dict(seg=t["seg"], aim=aim, cov=cov, z=Z0,
                               window=[int(cy0*CH), int(cx0*CH), REGION]),
                          open(os.path.join(OUT, f"meta_{TAG}_{si}_{wi}.json"), "w"))
                log(f"[{si}.{wi}] aim {aim:.2f} cov {cov:.2f} mapped")
        except Exception as e:
            log(f"[{si}] failed: {e}")
    json.dump(dict(done=True, n=len(SEGS_MAP), tag=TAG),
              open(os.path.join(OUT, "done.json"), "w"))
    log("TRAIN+REMAP DONE")
    time.sleep(86400)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
        time.sleep(86400)
