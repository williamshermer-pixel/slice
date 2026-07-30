"""SANITY — does our CPU port of the official ink model reproduce a
published detection? Run on an ink-dense window of a PHerc1667 segment
(the model's home scroll), compare to the published map.

Recipe per the model card: 62 depth layers, clip [0,200] float32,
256-px tiles, stride 128, sigmoid logits at quarter resolution,
average-blend overlaps.
"""
import os, sys, json, time
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("INK_TAG", "S")
import pack as P
import native as N

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "sanity_infer.png")
NT = 8          # 8 chunks = 1024 px at 2.258 um
WINDOW, STRIDE, DLAY = 256, 128, 62


def get_region():
    tg = [t for t in P.targets() if t["scroll"] == "PHerc1667"]
    for t0 in tg:
        ink, iy, ix = N.aim(t0, nt_l1=NT)
        if ink is None:
            continue
        t = dict(t0, seg=t0["seg"] + "@sanity")
        tile = N.aimed_fetch(t, NT, ink, iy, ix)
        if tile is None:
            continue
        d = np.load(P._cache_path(t["seg"]), allow_pickle=False)
        return t0, dict(vol=d["vol"], pk=int(d["pk"]), ink=d["ink"].astype(np.float32),
                        ds=float(d["ds"]), iy=int(d["iy"]), ix=int(d["ix"]))
    return None, None


def main():
    t0, R = get_region()
    if R is None:
        print("no region found")
        return
    vol, pk = R["vol"], R["pk"]
    D, H, W = vol.shape
    OFF = int(os.environ.get("INK_OFF", "0"))
    FLIP = os.environ.get("INK_FLIP") == "1"
    a = max(0, min(D - DLAY, pk - DLAY // 2 + OFF))
    # Model card: "intensity should already be in roughly [0, 1]" — feeding
    # 0..200 saturates the net into border artifacts (measured: interior
    # sigmoid 0.000, white grid at tile seams). Clip then scale.
    stack = np.clip(vol[a:a + DLAY].astype(np.float32), 0, 200) / 255.0
    if FLIP:
        stack = stack[::-1].copy()
    if stack.shape[0] < DLAY:
        pad = DLAY - stack.shape[0]
        stack = np.concatenate([stack, np.repeat(stack[-1:], pad, 0)], 0)
    print(f"segment {t0['seg']}  region {H}x{W}  layers {a}..{a+DLAY} of {D}", flush=True)

    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained("scrollprize/PHerc.1667-iteration-0",
                                      trust_remote_code=True).eval()
    torch.set_num_threads(os.cpu_count() or 8)

    Hq, Wq = H // 4, W // 4
    acc = np.zeros((Hq, Wq), np.float32)
    cnt = np.zeros((Hq, Wq), np.float32)
    ys = list(range(0, H - WINDOW + 1, STRIDE))
    xs = list(range(0, W - WINDOW + 1, STRIDE))
    n, t_start = 0, time.time()
    with torch.no_grad():
        for y in ys:
            for x in xs:
                tile = stack[:, y:y + WINDOW, x:x + WINDOW]
                tt = torch.from_numpy(tile).unsqueeze(0).unsqueeze(0)
                out = model(tt)
                pr = torch.sigmoid(out.logits)[0, 0].numpy()
                acc[y // 4:y // 4 + 64, x // 4:x // 4 + 64] += pr
                cnt[y // 4:y // 4 + 64, x // 4:x // 4 + 64] += 1
                n += 1
            print(f"  row y={y}: {n}/{len(ys)*len(xs)} tiles, "
                  f"{(time.time()-t_start)/max(n,1):.1f}s/tile", flush=True)
    pred = acc / np.maximum(cnt, 1)

    # published map on the same quarter-res grid
    ds = R["ds"]
    ink = R["ink"][R["iy"]:R["iy"] + int(H / ds), R["ix"]:R["ix"] + int(W / ds)]
    ink_q = np.array(Image.fromarray(ink.astype(np.uint8)).resize((Wq, Hq), Image.BILINEAR))
    tgt = (ink_q > 128)
    if 0.02 < tgt.mean() < 0.98:
        x_ = pred.ravel()
        o = np.argsort(x_)
        rk = np.empty(len(x_)); rk[o] = np.arange(1, len(x_) + 1)
        y_ = tgt.ravel()
        n1, n0 = int(y_.sum()), int((~y_).sum())
        auc = (rk[y_].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
        auc = max(auc, 1 - auc)
    else:
        auc = float("nan")
    r = float(np.corrcoef(pred.ravel(), ink_q.ravel())[0, 1])
    print(f"\nCONFIG off={OFF:+d} flip={int(FLIP)}  AUC vs published: {auc:.3f}   "
          f"r = {r:+.3f}   (coverage {tgt.mean()*100:.0f}%)")

    def norm(v):
        lo, hi = np.percentile(v, [2, 98])
        return (np.clip((v - lo) / max(hi - lo, 1e-9), 0, 1) * 255).astype(np.uint8)
    strip = np.concatenate([norm(ink_q), np.full((Hq, 4), 255, np.uint8),
                            norm(pred)], 1)
    img = Image.fromarray(strip).convert("RGB")
    dr = ImageDraw.Draw(img)
    dr.text((6, 6), f"published ink | our CPU inference   AUC {auc:.3f}",
            fill=(255, 200, 40))
    out = OUT.replace(".png", f"_o{OFF:+d}_f{int(FLIP)}.png")
    img.save(out)
    print(f"written: {out}")


if __name__ == "__main__":
    main()
