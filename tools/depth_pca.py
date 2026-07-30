"""DEPTH PCA — let the data choose which layers carry the signal.

THE ARGUMENT

Multispectral conservators do not look at bands one at a time. They run PCA
across bands, because the ink-versus-substrate separation usually lives in a
COMBINATION of bands and often no single band shows the text at all — the third
component does.

We have one spectral channel. But we have 109 depth layers through the sheet,
and every experiment in this project so far has collapsed depth before doing
anything: averaged a band, took the peak layer, and thrown the rest away. Nobody
has let the data choose which combination of depths carries the signal.

The ink is a ~15 um layer sitting on the sheet face. Papyrus fibre, sheet
curvature, and beam artefacts all have their own, different depth signatures.
That is exactly the situation where a linear combination across the axis
separates two things that neither end of the axis separates alone.

WHY THE BASIS IS FIXED, NOT PER-TILE

Running PCA per tile gives components in arbitrary order with arbitrary sign,
and "component 3 correlates with ink" then means nothing — component 3 is a
different thing on every tile. Worse, picking the best-correlating component per
tile is fitting the answer key one tile at a time.

So the basis is computed ONCE, on the tune scrolls only, pooled. That produces a
fixed bank of depth filters — actual loading vectors over depth — which are then
applied unchanged to held-out scrolls. The basis never sees held-out data and
never sees an ink label at all: PCA is unsupervised, so there is no answer key
to leak.

The components then become new features the pack can search over, which is the
other reason to build this. Until now the search could only recombine the eight
quantities that happened to get written. This raises the ceiling.

Usage
    python3 depth_pca.py --fit            build the basis from tune scrolls
    python3 depth_pca.py --validate 14    score each component held-out
"""
import os, sys, json, time
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("INK_OUT", os.path.join(HERE, "..", "out", "pca"))
BASIS = os.path.join(P.CACHE_DIR, "depth_basis.json")
os.makedirs(OUT, exist_ok=True)

K = 20             # layers kept each side of the sheet peak -> 41-layer window
NCOMP = 6
HP_UM = 1500.0     # in-plane high-pass before PCA. see note below.


def depth_stack(tile, k=K, hp_um=HP_UM):
    """The depth window around the sheet peak, per-layer normalised and
    in-plane high-passed.

    The high-pass is load-bearing. Without it PC1 is just "how bright is this
    sheet", which is the papyrus-condition signal that produced every false
    positive on the first overnight run. Removing structure coarser than a
    letter forces the components to describe fine depth behaviour instead.
    """
    pk, um = tile["pk"], tile["um"]
    a, b = pk-k, pk+k+1
    if a < 0 or b > tile["vol8"].shape[0]:
        return None
    w = P.layers(tile, a, b)
    r = max(1, int(round(hp_um/um/2)))
    out = np.empty_like(w)
    for i in range(w.shape[0]):
        L = w[i]
        L = L - P.box(L, r)
        s = L.std()
        out[i] = L/(s if s > 1e-9 else 1.0)
    return out


def fit_basis(n_tiles=12, k=K, ncomp=NCOMP):
    """Pool the depth covariance across tune-scroll tiles and eigen-decompose.

    The covariance is (2k+1) x (2k+1) — 41x41. Trivial to decompose. The cost is
    entirely in reading tiles, which the disk cache pays once.
    """
    tg = P.targets()
    by, tune, held, ts, hs = P.split_by_scroll(tg)
    print(f"fitting depth basis on TUNE scrolls only: {ts}")
    rng = np.random.default_rng(3)
    pick = list(rng.choice(tune, size=min(n_tiles, len(tune)), replace=False))
    pick = P.warm(pick)

    C = np.zeros((2*k+1, 2*k+1), np.float64)
    n = 0
    for t in pick:
        tile = P.load_tile(t)
        if tile is None:
            continue
        S = depth_stack(tile, k)
        if S is None:
            continue
        X = S.reshape(S.shape[0], -1)
        X = X - X.mean(1, keepdims=True)
        C += (X @ X.T)/X.shape[1]
        n += 1
    if n == 0:
        print("no usable tune tiles"); return None
    C /= n
    ev, V = np.linalg.eigh(C)
    order = np.argsort(ev)[::-1]
    ev, V = ev[order][:ncomp], V[:, order][:, :ncomp]

    # sign convention, so a component means the same thing on every tile:
    # make the largest-magnitude loading positive.
    for j in range(V.shape[1]):
        if V[np.argmax(np.abs(V[:, j])), j] < 0:
            V[:, j] *= -1

    var = ev/ev.sum()
    basis = dict(k=k, hp_um=HP_UM, n_tiles=n, scrolls=ts,
                 explained=[float(x) for x in var],
                 loadings=[[float(x) for x in V[:, j]] for j in range(V.shape[1])])
    json.dump(basis, open(BASIS, "w"), indent=1)
    print(f"  {n} tiles, {2*k+1} layers")
    for j in range(ncomp):
        print(f"  PC{j+1}  {var[j]*100:5.1f}% of variance")
    print(f"  written {BASIS}")
    _plot_loadings(V, var)
    return basis


def _plot_loadings(V, var):
    """Draw the loading vectors. A component that is flat across depth is a
    brightness term; one that flips sign through the sheet is a depth contrast,
    which is the interesting shape."""
    try:
        H, W = 260, 640
        img = Image.new("L", (W, H*V.shape[1]), 0)
        px = img.load()
        for j in range(V.shape[1]):
            v = V[:, j]
            m = max(np.abs(v).max(), 1e-9)
            for i in range(len(v)):
                x0 = int(i*W/len(v)); x1 = int((i+1)*W/len(v))
                y = int(H/2 - v[i]/m*(H/2-8)) + j*H
                for x in range(x0, x1):
                    for yy in range(min(y, j*H+H//2), max(y, j*H+H//2)+1):
                        px[x, yy] = 255
            for x in range(W):
                px[x, j*H+H//2] = 90
        img.save(os.path.join(OUT, "loadings.png"))
    except Exception:
        pass


_basis = None


def load_basis():
    global _basis
    if _basis is None:
        if not os.path.exists(BASIS):
            return None
        _basis = json.load(open(BASIS))
    return _basis


def pca_features(tile, b=None):
    """Project a tile onto the fixed depth basis. Returns one map per component."""
    b = b or load_basis()
    if b is None:
        raise RuntimeError("no basis — run: python3 depth_pca.py --fit")
    # Tolerate a short depth window. The sheet peak is not always centred in
    # the cropped volume, and demanding a full +/-k window silently returned {}
    # on those tiles, so every variant containing a PCA term was DISCARDED
    # rather than scored and PCA could never win regardless of merit. Where the
    # window is short the loadings are resampled onto the available range: an
    # approximation, but an unbiased one.
    k = int(b["k"])
    pk, nz = tile["pk"], tile["vol8"].shape[0]
    k_eff = min(k, pk, nz - pk - 1)
    if k_eff < 8:
        return {}
    S = depth_stack(tile, k_eff, b["hp_um"])
    if S is None:
        return {}
    X = S.reshape(S.shape[0], -1)
    X = X - X.mean(1, keepdims=True)
    src = np.linspace(0.0, 1.0, 2*k + 1)
    dst = np.linspace(0.0, 1.0, 2*k_eff + 1)
    F = {}
    for j, load in enumerate(b["loadings"]):
        w = np.array(load, np.float32)
        if k_eff != k:
            w = np.interp(dst, src, w).astype(np.float32)
            nrm = float(np.linalg.norm(w))
            w = w/(nrm if nrm > 1e-9 else 1.0)
        F[f"pca_c{j+1}"] = (w @ X).reshape(S.shape[1], S.shape[2])
    return F


PCA_NAMES = [f"pca_c{j+1}" for j in range(NCOMP)]


def validate(n_held=14):
    b = load_basis()
    if b is None:
        b = fit_basis()
        if b is None:
            return []
    tg = P.targets()
    by, tune, held, ts, hs = P.split_by_scroll(tg)
    print(f"\nheld-out scrolls {hs}")
    rng = np.random.default_rng(11)
    pick = list(rng.choice(held, size=min(n_held, len(held)), replace=False))
    print("held-out tiles:")
    pick = P.warm(pick)
    print("negative-control tiles (blank papyrus):")
    negs = P.warm(P.find_negatives(held, n=6))

    rows = []
    for j in range(len(b["loadings"])):
        nm = f"pca_c{j+1}"
        rs, ps = [], []
        for t in pick:
            tile = P.load_tile(t)
            if tile is None:
                continue
            try:
                f = pca_features(tile, b).get(nm)
            except Exception:
                continue
            if f is None:
                continue
            s = P.score_vs_ink(f, tile)
            if s:
                rs.append(s["r"]); ps.append(s["p"])
        if len(rs) < 4:
            print(f"  {nm} too few tiles"); continue
        rs = np.array(rs)
        sign = 1.0 if np.median(rs) > 0 else -1.0
        med = float(np.median(sign*rs))
        frac = float((np.array(ps) < 0.05).mean())
        nr = P.neg_control(lambda tl, _j=j: pca_features(tl, b).get(f"pca_c{_j+1}"), negs)
        fin = P.penalised(med, nr)
        rows.append(dict(feature=nm, explained=b["explained"][j], heldout_median=med,
                         frac_signif=frac, n=len(rs), negative_control=nr, penalised=fin))
        print(f"  {nm}  ({b['explained'][j]*100:4.1f}% var)  held-out r={med:+.3f}  "
              f"{frac*100:3.0f}% signif  n={len(rs):2d}  blank |r|="
              f"{nr if nr is None else round(nr,3)}  ->  penalised {fin:+.3f}", flush=True)
    json.dump(rows, open(os.path.join(OUT, "pca_validation.json"), "w"), indent=1)
    if rows:
        best = max(rows, key=lambda r: r["penalised"])
        print(f"\nbest after penalty: {best['feature']} {best['penalised']:+.3f}")
        print("note: a LOW-variance component scoring well is the interesting case —\n"
              "that is the multispectral result, where the signal is not the loudest thing.")
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    mode = a[0] if a else "--validate"
    t0 = time.time()
    if mode == "--fit":
        fit_basis(int(a[1]) if len(a) > 1 else 12)
    else:
        validate(int(a[1]) if len(a) > 1 else 14)
    print(f"{time.time()-t0:.0f}s")
