"""Depth-contrast score per segment, built on the path verified standalone.

Question: is there a readable SHEET here, or compressed mush?
Method: render a small strip along the surface normal, measure how much the
mean intensity varies through depth. Scroll 1's readable surface spans ~33 grey
levels. PHerc.1447/20250502205333 spans 0.72 — covered, but fused.
"""
import urllib.request, io, json, sys, traceback
import numpy as np
from PIL import Image

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH, GRIDN, T, STEP = 128, 8, 12, 20
VOL = {
    "PHerc0800": ("20250521135224-8.640um-1.2m-116keV-masked.zarr", 8.64),
    "PHerc1447": ("20250521151220-8.640um-1.2m-116keV-masked.zarr", 8.64),
    "PHerc1203": ("20250820131727-9.362um-1.2m-113keV-masked.zarr", 9.362),
    "PHerc0332": ("20251211183505-2.399um-0.2m-78keV-masked.zarr", 2.399),
}
g = lambda u, t=90: urllib.request.urlopen(u, timeout=t).read()


def up(a, f):
    h, w = a.shape
    yy = np.linspace(0, h - 1, h * f); xx = np.linspace(0, w - 1, w * f)
    y0 = np.floor(yy).astype(int); y1 = np.minimum(y0 + 1, h - 1); fy = (yy - y0)[:, None]
    x0 = np.floor(xx).astype(int); x1 = np.minimum(x0 + 1, w - 1); fx = (xx - x0)[None, :]
    return (a[np.ix_(y0, x0)] * (1 - fy) * (1 - fx) + a[np.ix_(y1, x0)] * fy * (1 - fx)
            + a[np.ix_(y0, x1)] * (1 - fy) * fx + a[np.ix_(y1, x1)] * fy * fx)


def score(scroll, pre):
    volfile, um = VOL[scroll]
    vol = f"{scroll}/volumes/{volfile}"   # the key needs the sample prefix
    X = np.array(Image.open(io.BytesIO(g(f"{B}/{pre}x.tif")))).astype(float)
    Y = np.array(Image.open(io.BytesIO(g(f"{B}/{pre}y.tif")))).astype(float)
    Z = np.array(Image.open(io.BytesIO(g(f"{B}/{pre}z.tif")))).astype(float)
    v = (X > 0) & (Y > 0) & (Z > 0)
    ii = np.pad(np.cumsum(np.cumsum(v.astype(int), 0), 1), ((1, 0), (1, 0)))
    spot = None
    for j in range(0, max(1, v.shape[0] - GRIDN), 2):
        for i in range(0, max(1, v.shape[1] - GRIDN), 2):
            if ii[j+GRIDN, i+GRIDN] - ii[j, i+GRIDN] - ii[j+GRIDN, i] + ii[j, i] == GRIDN*GRIDN:
                spot = (j, i); break
        if spot is not None: break
    if spot is None:
        return {"err": "no valid patch"}
    j, i = spot
    Xf, Yf, Zf = [up(A[j:j+GRIDN, i:i+GRIDN], STEP) for A in (X, Y, Z)]
    Tux, Tuy, Tuz = [np.gradient(A, axis=1) for A in (Xf, Yf, Zf)]
    Tvx, Tvy, Tvz = [np.gradient(A, axis=0) for A in (Xf, Yf, Zf)]
    Nx = Tuy*Tvz - Tuz*Tvy; Ny = Tuz*Tvx - Tux*Tvz; Nz = Tux*Tvy - Tuy*Tvx
    L = np.sqrt(Nx**2 + Ny**2 + Nz**2) + 1e-9
    Nx, Ny, Nz = Nx/L, Ny/L, Nz/L
    d = np.arange(-T, T + 1.0)
    pz = Zf[None] + d[:, None, None]*Nz[None]
    py = Yf[None] + d[:, None, None]*Ny[None]
    px = Xf[None] + d[:, None, None]*Nx[None]
    lo = [int(np.floor(a.min()))-1 for a in (pz, py, px)]
    hi = [int(np.ceil(a.max()))+2 for a in (pz, py, px)]
    cz0, cy0, cx0 = [l//CH for l in lo]; cz1, cy1, cx1 = [(h//CH)+1 for h in hi]
    n = (cz1-cz0)*(cy1-cy0)*(cx1-cx0)
    if n > 80:
        return {"err": f"{n} chunks, too big"}
    dense = np.zeros(((cz1-cz0)*CH, (cy1-cy0)*CH, (cx1-cx0)*CH), np.uint8)
    got = 0
    for cz in range(cz0, cz1):
        for cy in range(cy0, cy1):
            for cx in range(cx0, cx1):
                try:
                    b = g(f"{B}/{vol}/0/{cz}/{cy}/{cx}", 120)
                    if len(b) == CH**3:
                        got += 1
                        dense[(cz-cz0)*CH:(cz-cz0+1)*CH, (cy-cy0)*CH:(cy-cy0+1)*CH,
                              (cx-cx0)*CH:(cx-cx0+1)*CH] = np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                except Exception:
                    pass
    if got == 0:
        return {"err": "no chunks"}
    z0 = np.clip((pz - cz0*CH).astype(int), 0, dense.shape[0]-1)
    y0 = np.clip((py - cy0*CH).astype(int), 0, dense.shape[1]-1)
    x0 = np.clip((px - cx0*CH).astype(int), 0, dense.shape[2]-1)
    out = dense[z0, y0, x0].astype(np.float32)
    prof = out.mean(axis=(1, 2))
    return {"span": float(prof.max()-prof.min()), "filled": float((out > 0).mean()),
            "chunks": f"{got}/{n}", "thick_um": (2*T+1)*um}


def find_pre(scroll, seg):
    base = f"{scroll}/segments/{seg}/mesh/intermediate/"
    for nm in ("tifxyz_original/", "tifxyz_normalized/", "tifxyz/"):
        try:
            urllib.request.urlopen(urllib.request.Request(f"{B}/{base}{nm}meta.json", method="HEAD"), timeout=20)
            return base + nm
        except Exception:
            continue
    return None


if __name__ == "__main__":
    rows = json.load(open("segment_coverage.json"))
    cands = [r for r in rows if (r.get("livefrac") or 0) > 0.30]
    print(f"scoring {len(cands)} segments\n")
    print(f"{'scroll':10s} {'segment':34s} {'live%':>6s} {'span':>7s}  verdict")
    print("-" * 82)
    out = []
    for r in cands:
        pre = find_pre(r["scroll"], r["seg"])
        if not pre:
            print(f"{r['scroll']:10s} {r['seg'][:34]:34s} {100*r['livefrac']:5.1f}%       -  no tifxyz")
            continue
        try:
            s = score(r["scroll"], pre)
        except Exception as e:
            s = {"err": f"{type(e).__name__}: {e}"}
        if "err" in s:
            print(f"{r['scroll']:10s} {r['seg'][:34]:34s} {100*r['livefrac']:5.1f}%       -  {s['err']}")
            continue
        vd = ("SHEET" if s["span"] >= 8 else "marginal" if s["span"] >= 3 else "compressed / no sheet")
        print(f"{r['scroll']:10s} {r['seg'][:34]:34s} {100*r['livefrac']:5.1f}% {s['span']:7.2f}  {vd}")
        out.append({**r, **s, "verdict": vd})
    out.sort(key=lambda x: -x["span"])
    json.dump(out, open("segment_depth.json", "w"), indent=1)
    print("\n" + "="*82)
    print("RANKED BY DEPTH CONTRAST — Scroll 1's readable surface scores ~33")
    print("="*82)
    for r in out[:12]:
        print(f"  {r['scroll']:10s} {r['seg'][:36]:36s} span {r['span']:6.2f}  "
              f"live {100*r['livefrac']:5.1f}%  {r['verdict']}")
    if out:
        best = out[0]
        print(f"\nbest: {best['scroll']}/{best['seg']}  span {best['span']:.2f}")
