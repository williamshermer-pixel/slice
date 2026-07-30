"""POD FIX — make our renderer produce LETTERS on ground truth, before
anything else gets built. One GP-segment window with known-legible text;
test matrix over the four suspects from the letterform control:

  A. depth band: 6 start-layers across the 116-layer stack (the field's
     recipe counts from the sheet face; we had been centring blindly)
  B. model: iteration-5 (mature) vs iteration-0 (what we had used)
  C. aggregation: Gaussian-weighted logit blending vs flat averaging

Every variant scored (AUC vs published) AND rendered into one contact
sheet — letters visibly appearing is the pass condition, not the number.
"""
import io, os, json, time, urllib.request
import concurrent.futures as cf
import numpy as np

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
SEG = "PHercParis4/segments/20230702185753/"
SV = SEG + "surface-volumes/1.129um-0.23m-78keV-volume-20260608103018-L1.zarr/"
INK = SEG + ("ink-detection/downsampled/PHercParis4-20230702185753-1.129um-0.23m-"
             "78keV-volume-20260608103018-L1-__INKTAIL__")
OUT = "/workspace/out"
os.makedirs(OUT, exist_ok=True)
CH = 128
REGION, WINDOW, STRIDE, DLAY = 2048, 256, 64, 62


def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "progress.txt"), "a").write(m + "\n")


def get(u, t=120):
    return urllib.request.urlopen(u, timeout=t).read()


def main():
    from PIL import Image, ImageDraw
    import torch
    from transformers import AutoModel

    ink = np.array(Image.open(io.BytesIO(get(f"{B}/__INKFULL__")))).astype(np.float32)
    if ink.ndim == 3:
        ink = ink.mean(2)
    za = json.loads(get(f"{B}/{SV}0/.zarray").decode())
    D, HH, WW = za["shape"]
    ds = WW / ink.shape[1]
    w = int(round(REGION / ds))
    m = (ink > 128).astype(np.float32)
    cs = m.cumsum(0).cumsum(1)
    s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
    c = s / float(w * w)
    c[c < 0.15] = np.inf
    iy, ix = np.unravel_index(int(np.abs(c - 0.40).argmin()), c.shape)
    cy0 = max(0, min(HH//CH - REGION//CH, int(round(iy * ds / CH))))
    cx0 = max(0, min(WW//CH - REGION//CH, int(round(ix * ds / CH))))
    nt = REGION // CH
    log(f"stack depth D={D}; window chunks ({cy0},{cx0})")

    full = np.zeros((D, REGION, REGION), np.uint8)
    got = [0]
    def g(cy, cx):
        try:
            b = get(f"{B}/{SV}0/0/{cy}/{cx}")
            if len(b) == D*CH*CH:
                a = np.frombuffer(b, np.uint8).reshape(D, CH, CH)
                full[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = a
                got[0] += 1
        except Exception:
            pass
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda q: g(*q), [(cy0+j, cx0+i) for j in range(nt) for i in range(nt)]))
    log(f"fetched {got[0]}/{nt*nt} chunks (full {D}-layer stack)")

    ink_q = np.array(Image.fromarray(
        ink[int(cy0*CH/ds):int(cy0*CH/ds)+w, int(cx0*CH/ds):int(cx0*CH/ds)+w]
        .astype(np.uint8)).resize((REGION//4, REGION//4), Image.BILINEAR))
    tgt = ink_q > 128

    # Gaussian window for weighted blending
    gy, gx = np.mgrid[0:64, 0:64]
    gw = np.exp(-(((gy-31.5)/18)**2 + ((gx-31.5)/18)**2)/2).astype(np.float32)

    def run(model, torch, z0, gaussian):
        Hq = REGION // 4
        acc = np.zeros((Hq, Hq), np.float32)
        cnt = np.zeros((Hq, Hq), np.float32)
        coords = [(y, x) for y in range(0, REGION-WINDOW+1, STRIDE)
                  for x in range(0, REGION-WINDOW+1, STRIDE)]
        wgt = gw if gaussian else np.ones((64, 64), np.float32)
        with torch.no_grad():
            for b0 in range(0, len(coords), 16):
                bc = coords[b0:b0+16]
                tiles = np.stack([np.clip(full[z0:z0+DLAY, y:y+WINDOW, x:x+WINDOW]
                                          .astype(np.float32), 0, 200)/255.0
                                  for y, x in bc])
                tt = torch.from_numpy(tiles).unsqueeze(1).cuda()
                pr = model(tt).logits[:, 0].float().cpu().numpy()
                for (y, x), p in zip(bc, pr):
                    acc[y//4:y//4+64, x//4:x//4+64] += p*wgt
                    cnt[y//4:y//4+64, x//4:x//4+64] += wgt
        pred = 1.0/(1.0+np.exp(-(acc/np.maximum(cnt, 1e-6))))
        x_ = pred.ravel(); o = np.argsort(x_)
        rk = np.empty(len(x_)); rk[o] = np.arange(1, len(x_)+1)
        yv = tgt.ravel(); n1, n0 = int(yv.sum()), int((~yv).sum())
        auc = (rk[yv].sum()-n1*(n1+1)/2)/(n1*n0)
        return pred, float(max(auc, 1-auc))

    results = []
    z0s = [0, 13, 27, max(0, D//2-31), 42, min(D-DLAY, 54)]
    z0s = sorted(set(int(z) for z in z0s))
    for name in ("scrollprize/PHerc.1667-iteration-5",
                 "scrollprize/PHerc.1667-iteration-0"):
        model = AutoModel.from_pretrained(name, trust_remote_code=True).eval().cuda()
        for z0 in z0s:
            for gauss in (True, False):
                if not gauss and z0 != z0s[0]:
                    continue          # flat-avg tested once per model
                t0 = time.time()
                pred, auc = run(model, torch, z0, gauss)
                tag = f"{name.split('-')[-1]}_z{z0}_{'gauss' if gauss else 'flat'}"
                np.save(os.path.join(OUT, f"fix_{tag}.npy"), pred)
                results.append((auc, tag))
                log(f"{tag}: AUC {auc:.3f} ({time.time()-t0:.0f}s)")
        del model
        torch.cuda.empty_cache()

    results.sort(reverse=True)
    json.dump(dict(done=True, best=results[0][1], best_auc=results[0][0],
                   table=[[t, a] for a, t in results]),
              open(os.path.join(OUT, "done.json"), "w"))

    # contact sheet: published + every variant
    def norm(a):
        lo, hi = np.percentile(a, [2, 99])
        return (np.clip((a-lo)/max(hi-lo, 1e-9), 0, 1)*255).astype(np.uint8)
    S = 340
    tiles = [np.array(Image.fromarray(norm(ink_q.astype(np.float32))).resize((S, S)))]
    labels = ["PUBLISHED"]
    for a, tag in results:
        p = np.load(os.path.join(OUT, f"fix_{tag}.npy"))
        tiles.append(np.array(Image.fromarray(norm(p)).resize((S, S))))
        labels.append(f"{tag} {a:.3f}")
    cols = 4
    while len(tiles) % cols:
        tiles.append(np.zeros((S, S), np.uint8)); labels.append("")
    rows = []
    for i in range(0, len(tiles), cols):
        rows.append(np.concatenate(tiles[i:i+cols], 1))
    sheet = Image.fromarray(np.concatenate(rows, 0)).convert("RGB")
    d = ImageDraw.Draw(sheet)
    for i, lab in enumerate(labels):
        d.text(((i % cols)*S+6, (i//cols)*S+6, ), lab, fill=(255, 200, 40))
    sheet.save(os.path.join(OUT, "fix_sheet.png"))
    log("DONE — fix_sheet.png")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        open(os.path.join(OUT, "error.txt"), "w").write(traceback.format_exc())
        log("FAILED")
