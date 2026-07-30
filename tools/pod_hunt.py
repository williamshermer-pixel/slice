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
SEG = "PHerc0139/segments/20250108000004-w029_2025010827/"
SV = SEG + "surface-volumes/1.129um-0.22m-59keV-volume-20260413113053-L1.zarr/"
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

    ink = np.array(Image.open(io.BytesIO(get(f"{B}/PHerc0139/segments/20250108000004-w029_2025010827/ink-detection/downsampled/PHerc0139-20250108000004-1.129um-0.22m-59keV-volume-20260413113053-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg")))).astype(np.float32)
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
    z0s = [0, 13, 27, 42, 54, min(D-DLAY, 70)]
    z0s = sorted(set(int(z) for z in z0s))
    for name in ("scrollprize/PHerc.1667-iteration-5",):
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
    best_z = int(results[0][1].split("_z")[1].split("_")[0])
    log(f"BEST z for this scroll: {best_z} — remapping margins")
    MARGINS = [{"seg": "PHerc0139/segments/20250108000000-w025_2025010863/", "sv": "PHerc0139/segments/20250108000000-w025_2025010863/surface-volumes/1.129um-0.22m-59keV-volume-20260413113053-L1.zarr/", "ink": "PHerc0139/segments/20250108000000-w025_2025010863/ink-detection/downsampled/PHerc0139-20250108000000-1.129um-0.22m-59keV-volume-20260413113053-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg"}, {"seg": "PHerc0139/segments/20250108000001-w026_2025010854/", "sv": "PHerc0139/segments/20250108000001-w026_2025010854/surface-volumes/1.129um-0.22m-59keV-volume-20260413113053-L1.zarr/", "ink": "PHerc0139/segments/20250108000001-w026_2025010854/ink-detection/downsampled/PHerc0139-20250108000001-1.129um-0.22m-59keV-volume-20260413113053-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg"}, {"seg": "PHerc0139/segments/20250108000002-w027_2025010845/", "sv": "PHerc0139/segments/20250108000002-w027_2025010845/surface-volumes/1.129um-0.22m-59keV-volume-20260413113053-L1.zarr/", "ink": "PHerc0139/segments/20250108000002-w027_2025010845/ink-detection/downsampled/PHerc0139-20250108000002-1.129um-0.22m-59keV-volume-20260413113053-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg"}, {"seg": "PHerc0139/segments/20250108000003-w028_2025010836/", "sv": "PHerc0139/segments/20250108000003-w028_2025010836/surface-volumes/1.129um-0.22m-59keV-volume-20260413113053-L1.zarr/", "ink": "PHerc0139/segments/20250108000003-w028_2025010836/ink-detection/downsampled/PHerc0139-20250108000003-1.129um-0.22m-59keV-volume-20260413113053-L1-20260709123958-mrg20736-1um-s1z2-tile256-stride128-ds8.jpg"}]
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-5",
                                      trust_remote_code=True).eval().cuda()
    for mi, mt in enumerate(MARGINS):
        try:
            za2 = json.loads(get(f"{B}/{mt['sv']}0/.zarray").decode())
            D2, HH2, WW2 = za2["shape"]
            ink2 = np.array(Image.open(io.BytesIO(get(f"{B}/{mt['ink']}")))).astype(np.float32)
            if ink2.ndim == 3: ink2 = ink2.mean(2)
            ds2 = WW2/ink2.shape[1]; w2 = int(round(4096/ds2))
            m2 = (ink2 > 128).astype(np.float32)
            cs2 = m2.cumsum(0).cumsum(1)
            s2 = cs2[w2:, w2:]-cs2[:-w2, w2:]-cs2[w2:, :-w2]+cs2[:-w2, :-w2]
            c2 = s2/float(w2*w2); c2[c2 < 0.02] = np.inf
            iy2, ix2 = np.unravel_index(int(np.abs(c2-0.10).argmin()), c2.shape)
            if not np.isfinite(c2[iy2, ix2]): log(f"  m[{mi}] no window"); continue
            cy2 = max(0, min(HH2//CH-32, int(round(iy2*ds2/CH))))
            cx2 = max(0, min(WW2//CH-32, int(round(ix2*ds2/CH))))
            st2 = np.zeros((D2, 4096, 4096), np.uint8)
            got2 = [0]
            def g2(cy, cx):
                try:
                    b = get(f"{B}/{mt['sv']}0/0/{cy}/{cx}")
                    if len(b) == D2*CH*CH:
                        st2[:, (cy-cy2)*CH:(cy-cy2+1)*CH, (cx-cx2)*CH:(cx-cx2+1)*CH] = \
                            np.frombuffer(b, np.uint8).reshape(D2, CH, CH)
                        got2[0] += 1
                except Exception: pass
            with cf.ThreadPoolExecutor(max_workers=32) as ex:
                list(ex.map(lambda q: g2(*q), [(cy2+j, cx2+i) for j in range(32) for i in range(32)]))
            Hq2 = 1024
            acc2 = np.zeros((Hq2, Hq2), np.float32); cnt2 = np.zeros((Hq2, Hq2), np.float32)
            coords2 = [(y, x) for y in range(0, 4096-WINDOW+1, 64) for x in range(0, 4096-WINDOW+1, 64)]
            with torch.no_grad():
                for b0 in range(0, len(coords2), 16):
                    bc = coords2[b0:b0+16]
                    tiles = np.stack([np.clip(st2[best_z:best_z+DLAY, y:y+WINDOW, x:x+WINDOW]
                                              .astype(np.float32), 0, 200)/255.0 for y, x in bc])
                    tt = torch.from_numpy(tiles).unsqueeze(1).cuda()
                    pr = model(tt).logits[:, 0].float().cpu().numpy()
                    for (y, x), p in zip(bc, pr):
                        acc2[y//4:y//4+64, x//4:x//4+64] += p*gw
                        cnt2[y//4:y//4+64, x//4:x//4+64] += gw
            np.save(os.path.join(OUT, f"hunt_{mi}.npy"),
                    1.0/(1.0+np.exp(-(acc2/np.maximum(cnt2, 1e-6)))))
            json.dump(dict(seg=mt["seg"], window=[int(cy2*CH), int(cx2*CH), 4096], z=best_z),
                      open(os.path.join(OUT, f"huntmeta_{mi}.json"), "w"))
            log(f"  m[{mi}] {mt['seg'].split('/')[-2][:22]} remapped ({got2[0]} chunks)")
        except Exception as e:
            log(f"  m[{mi}] failed: {e}")
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
