"""DIFFERENTIAL 0139 — ours-hot vs published-cold on the tuned-eyes maps.

Published 0139 maps are binarized (p50=0, faint band 0.3-0.5%): everything
marginal was discarded at publication. The hunting ground is where OUR raw
map is confident and the published map is empty. Gates use 0139's OWN
measured hand (letters median 1.09 mm, pitch 4.57 mm, advance 0.70 mm) —
per-scribe doctrine. Output: ranked candidates + gallery renders.

Run after `fleet_lostbook.py harvest`:  python3 tools/differential_0139.py
"""
import glob, io, json, os, urllib.request
import numpy as np
from PIL import Image, ImageDraw

# Scroll 1 ds8 ink maps are 200+ MP, above PIL's decompression-bomb
# guard. Trusted reads from the project's own public bucket.
Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- per-scribe configuration ------------------------------------------
# The hand is NOT shared between scrolls (PHerc0139 writes a third the size
# of Scroll 1), so every constant below is measured per scroll and selected
# by env. Applying one scroll's ruler to another manufactures candidates --
# that error produced two retractions in this project.
HANDS = {
    # scroll:      (outdir,   letter_mm, lo_mm, hi_mm, adv_mm, pitch_mm, mode)
    # mode: "shape" where the model resolves stroke structure (3 mm hand);
    # "envelope" where it only resolves letter-sized mass (measured on 0139:
    # shape recovers 9.9% of known letters there, too blind to interpret).
    "PHerc0139":   ("lostbook", 1.09, 0.70, 2.20, 0.70, 4.57, "envelope"),
    "PHercParis4": ("scroll1",  3.00, 1.80, 4.60, 1.86, 6.18, "shape"),
}
SCROLL = os.environ.get("SCROLL", "PHerc0139")
if SCROLL not in HANDS:
    raise SystemExit(f"no measured hand for {SCROLL} — measure it first "
                     f"(per-scribe doctrine); known: {list(HANDS)}")
_OUTDIR, LETTER_MM, _LO, _HI, _ADV, _PITCH, MODE = HANDS[SCROLL]
MODE = os.environ.get("MODE", MODE)

LB = os.path.join(ROOT, "out", os.environ.get("OUTDIR", _OUTDIR))
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
UM_PER_PX = 9.032          # pred is quarter-res of the 2.258 um -L1 canvas
MM = 1000.0 / UM_PER_PX    # px per mm (~110.7)
LETTER_LO, LETTER_HI = int(_LO * MM), int(_HI * MM)
ADVANCE = _ADV * MM
PITCH = _PITCH * MM
OURS_PCT, PUB_COLD = 96.0, 60.0

TARGETS = {t["seg"]: t for t in
           json.load(open(os.path.join(ROOT, "findings", "targets.json")))
           if t["scroll"] == SCROLL}
_ink_cache = {}


def fetch(u, t=120):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=t).read()


def pub_crop(meta):
    """Published ink map crop aligned to our pred (1024^2 at UM_PER_PX).

    ds is measured (volume width / jpeg width, ~8.000 but not exactly) so the
    crop cannot drift against our canvas-coordinate window.
    """
    t = TARGETS[meta["seg"]]
    if t["seg"] not in _ink_cache:
        a = np.array(Image.open(io.BytesIO(fetch(f"{B}/{t['ink']}")))
                     ).astype(np.float32)
        if a.ndim == 3:
            a = a.mean(2)
        WW = json.loads(fetch(f"{B}/{t['sv']}0/.zarray").decode())["shape"][2]
        _ink_cache[t["seg"]] = (a, WW / a.shape[1])
    ink, ds = _ink_cache[t["seg"]]
    y0, x0, R = meta["window"]
    iy0, ix0 = int(round(y0 / ds)), int(round(x0 / ds))
    n = int(round(R / ds))
    c = ink[iy0:iy0 + n, ix0:ix0 + n]
    if c.shape != (n, n):                      # clamp at segment edge
        pad = np.zeros((n, n), np.float32)
        pad[:c.shape[0], :c.shape[1]] = c
        c = pad
    return np.array(Image.fromarray(c).resize((1024, 1024), Image.BILINEAR))


def components(mask):
    """4-connected component labelling, pure numpy/scipy-free flood fill."""
    lab = np.zeros(mask.shape, np.int32)
    cur = 0
    comps = []
    for sy, sx in zip(*np.nonzero(mask & (lab == 0))):
        if lab[sy, sx]:
            continue
        cur += 1
        stack = [(sy, sx)]
        lab[sy, sx] = cur
        px = []
        while stack:
            y, x = stack.pop()
            px.append((y, x))
            for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if (0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1]
                        and mask[ny, nx] and not lab[ny, nx]):
                    lab[ny, nx] = cur
                    stack.append((ny, nx))
        ys = [p[0] for p in px]; xs = [p[1] for p in px]
        h, w = max(ys) - min(ys) + 1, max(xs) - min(xs) + 1
        comps.append(dict(area=len(px), y0=min(ys), y1=max(ys),
                          x0=min(xs), x1=max(xs),
                          cy=float(np.mean(ys)), cx=float(np.mean(xs)),
                          fill=round(len(px) / float(h * w), 3),
                          aspect=round(w / float(h), 3)))
    return comps


def is_strokelike(c):
    """SHAPE gate — the discrimination every prior candidate failed.

    Letters are thin strokes inside their bounding box; damage patches and
    merged model blocks are solid. Measured on Scroll 1's real letterforms,
    ink components fill 15-55% of their box and sit near square aspect.
    A solid square (fill ~1.0) is a condition patch or a grid artifact,
    which is precisely what killed the Zone and the fleet-day candidates.
    """
    return 0.12 <= c["fill"] <= 0.60 and 0.35 <= c["aspect"] <= 2.8


def rhythm(mask, comps):
    """Advance-autocorrelation of the column projection near 0.70 mm."""
    if len(comps) < 2:
        return 0.0
    col = mask.sum(0).astype(np.float32)
    col -= col.mean()
    if col.std() < 1e-6:
        return 0.0
    ac = np.correlate(col, col, "full")[len(col) - 1:]
    ac /= max(ac[0], 1e-9)
    lo, hi = int(ADVANCE * 0.6), int(ADVANCE * 1.5)
    return float(ac[lo:hi].max())


def defog(p):
    """max-stretch -> sigmoid(gain 22 around p70) -> unsharp r6/1.4."""
    g = np.clip(np.nan_to_num(p), 0, 1)
    g = g / max(g.max(), 1e-9)
    s = 1.0 / (1.0 + np.exp(-22.0 * (g - np.percentile(g, 70))))
    im = Image.fromarray((s * 255).astype(np.uint8))
    from PIL import ImageFilter
    blur = im.filter(ImageFilter.GaussianBlur(6))
    arr = np.asarray(im).astype(np.float32)
    sharp = np.clip(arr + 1.4 * (arr - np.asarray(blur, np.float32)), 0, 255)
    return sharp.astype(np.uint8)


def floor_value():
    """Absolute confidence floor, calibrated on his KNOWN ink by
    tools/calibrate_floor.py (operating point: 0.2% FPR on known-blank
    papyrus). Without this the search is relative-only and the spatial null
    kills everything it finds -- measured, 2026-07-30."""
    p = os.path.join(LB, "floor.json")
    if not os.path.exists(p):
        raise SystemExit("run tools/calibrate_floor.py first — a relative-only "
                         "differential does not survive its own null test")
    return json.load(open(p))["floor"]


def hot_mask(ours, floor=None):
    """Hot = relatively hottest AND absolutely confident.

    The relative half (top 4%) always selects 4% of pixels whether ink exists
    or not; the absolute half is what makes a margin hit mean something.
    Saturation guard: when pixels tie at the max, `> p96` is EMPTY and the
    search goes silently blind, so fall back to >= on the same threshold.
    """
    thr = np.percentile(ours, OURS_PCT)
    hot = ours > thr
    if not hot.any():
        hot = ours >= thr
    if floor is None:
        floor = floor_value()
    return hot & (ours >= floor)


def gate(ours, pub, floor=None, mode=None):
    """The differential gates. Production path — the calibration harness
    calls THIS, so the test can never drift from what judges real maps.

    mode="shape":    require stroke topology (fill/aspect). Correct for a
                     3 mm hand like Scroll 1's. MEASURED on 0139: recovers
                     only 9.9% of his known letters -> 26% power on ten
                     hidden letters, i.e. too blind to interpret.
    mode="envelope": size only, allowing merged runs up to three letters.
                     Respects the resolution ceiling at his 1.09 mm hand
                     (READER_DESIGN's envelope mode). Discrimination then
                     comes from the ABSOLUTE floor plus a mandatory spatial
                     null, not from shape.
    """
    mode = MODE if mode is None else mode
    mask = hot_mask(ours, floor) & (pub < PUB_COLD)
    hi = LETTER_HI if mode == "shape" else int(3 * LETTER_HI)
    sized = [c for c in components(mask)
             if c["area"] >= 200
             and LETTER_LO <= max(c["y1"]-c["y0"], c["x1"]-c["x0"]) <= hi]
    comps = [c for c in sized if is_strokelike(c)] if mode == "shape" else sized
    return mask, comps, rhythm(mask, comps), len(sized)


def analyze(mp):
    tag = os.path.basename(mp)[4:-4]          # sX_si_wi
    meta = json.load(open(os.path.join(LB, f"meta_{tag}.json")))
    ours = np.load(mp)
    pub = pub_crop(meta)
    called = pub > 128
    mask, comps, r, n_sized = gate(ours, pub)
    n = len(comps)
    # line-end signature: comps within one line pitch of called text
    adj = 0.0
    if n and called.any():
        cy, cx = np.nonzero(called)
        pts = np.stack([cy, cx], 1)[::17]          # subsample for speed
        near = 0
        for c in comps:
            d = np.hypot(pts[:, 0]-c["cy"], pts[:, 1]-c["cx"]).min()
            near += d < PITCH
        adj = near / n
    passes = 2 <= n <= 9
    # adjacency is NOT scored: every aimed window requires >=2% nearby ink by
    # construction, so adj==1.0 is guaranteed and carries no information.
    score = (n if passes else 0) * (1 + r)
    return dict(tag=tag, seg=meta["seg"].split("/")[-2], aim=meta["aim"],
                window=meta["window"], n_comps=n, n_sized=n_sized,
                rhythm=round(r, 3), adjacency=round(adj, 3),
                passes=bool(passes), score=round(float(score), 3),
                fills=[c["fill"] for c in comps]), ours, pub, mask, comps


def render(res, ours, pub, mask, comps, path):
    d = defog(ours)
    tex = np.load(os.path.join(LB, f"tex_{res['tag']}.npy"))
    panes = [tex, pub.astype(np.uint8), d]
    rgb = np.stack([d]*3, -1)
    rgb[mask] = [255, 180, 40]
    W = 512
    row = Image.new("RGB", (W*4, W+28), (10, 10, 11))
    for i, p in enumerate(panes):
        row.paste(Image.fromarray(p).resize((W, W)).convert("RGB"), (i*W, 28))
    ov = Image.fromarray(rgb).resize((W, W))
    dr = ImageDraw.Draw(ov)
    for c in comps:
        dr.rectangle([c["x0"]/2, c["y0"]/2, c["x1"]/2, c["y1"]/2],
                     outline=(255, 80, 60), width=2)
    row.paste(ov, (3*W, 28))
    hd = ImageDraw.Draw(row)
    hd.text((8, 7), f"{res['seg']}  aim {res['aim']:.2f}  "
            f"sized {res['n_sized']}->stroke {res['n_comps']}  "
            f"fill {res['fills']}  rhythm {res['rhythm']}  "
            f"adj {res['adjacency']}  |  papyrus - published - ours(defog) - "
            f"differential", fill=(233, 229, 219))
    row.save(path)


def main():
    maps = sorted(glob.glob(os.path.join(LB, "map_s*.npy")))
    print(f"{len(maps)} maps")
    results, keep = [], []
    for mp in maps:
        try:
            res, ours, pub, mask, comps = analyze(mp)
            results.append(res)
            flag = "  <-- CANDIDATE" if res["passes"] else ""
            print(f"{res['seg'][:26]:26} aim {res['aim']:.2f} "
                  f"comps {res['n_comps']:3d} rhythm {res['rhythm']:.2f} "
                  f"adj {res['adjacency']:.2f}{flag}")
            if res["passes"]:
                keep.append((res["score"], res, ours, pub, mask, comps))
        except Exception as e:
            print(f"{os.path.basename(mp)}: FAILED {e}")
    keep.sort(key=lambda k: -k[0])
    for rank, (sc, res, ours, pub, mask, comps) in enumerate(keep):
        render(res, ours, pub, mask, comps,
               os.path.join(LB, f"candidate_{rank:02d}_{res['tag']}.png"))
    json.dump(dict(n_maps=len(maps), results=results,
                   candidates=[k[1] for k in keep]),
              open(os.path.join(LB, "differential.json"), "w"), indent=1)
    print(f"\n{len(keep)} windows pass gates -> renders + differential.json")
    if keep:
        rows = [Image.open(os.path.join(LB, f"candidate_{i:02d}_{k[1]['tag']}.png"))
                for i, k in enumerate(keep[:8])]
        W = rows[0].width
        sheet = Image.new("RGB", (W, sum(r.height for r in rows)), (10, 10, 11))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height
        sheet.save(os.path.join(LB, "differential_gallery.png"))
        print("gallery -> out/lostbook/differential_gallery.png")


if __name__ == "__main__":
    main()
