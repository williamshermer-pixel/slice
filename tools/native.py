"""NATIVE v2 — the physics features at the resolution that samples the ink.

Bucket audit 2026-07-28: 17 segments publish a genuine 1.129 um surface
volume beside the `-L1` (2.258 um) product this project always read. The
field documents that text legible at 1.1 um is partially lost at 2.4 um.

v1 lesson (findings/native_rerun.json): a dead-centre crop misses the text —
these segments keep their ink off-centre, so 0139/1667 scored cov=0.0000 and
ten fetches died on absent chunks (sparse volumes; centre never written).
v2 AIMS the crop at the ink-dense window of the published map, for BOTH
sides of the pair:

    L1  at nt=2 (256 px @ 2.258 um)  ->  32x32 aligned grid
    nat at nt=4 (512 px @ 1.129 um)  ->  32x32 aligned grid

Same physical window, same grid, same params, same nulls. The only variable
is resolution. Writes findings/native_rerun2.json.

Usage: python3 native.py [--discover]
"""
import os, sys, json, time, io
import numpy as np
from PIL import Image
import concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

_argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    import dogs as D
finally:
    sys.argv = _argv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "findings", "native_rerun2.json")
SCROLLS = ("PHerc0814", "PHerc1667", "PHerc0139")
CH = P.CH

FEATURES = ["fringe", "ridge", "rti_height", "rti_specvar", "rti_slope",
            "weave_fill", "weave_amp", "sharp", "offaxis", "hfenergy"]
N_DRAWS = 2


def discover():
    import re
    tg = P.targets()
    pairs, seen = [], set()
    for t in tg:
        if t["scroll"] not in SCROLLS or "surface-volumes/" not in t["sv"]:
            continue
        svdir = t["sv"].split("surface-volumes/")[0] + "surface-volumes/"
        if svdir in seen:
            continue
        seen.add(svdir)
        try:
            xml = P.get(f"{P.B}/?list-type=2&prefix={svdir}&delimiter=/", 60).decode()
        except Exception:
            continue
        for m in re.finditer(r"<Prefix>([^<]+\.zarr/)</Prefix>", xml):
            name = m.group(1)[len(svdir):]
            if name.startswith("1.129um") and "-L1" not in name:
                tag = os.environ.get("INK_TAG", "3")
                nt_ = dict(t, sv=svdir + name, seg=t["seg"] + "@nat" + tag, um=1.129)
                l1_ = dict(t, seg=t["seg"] + "@l1" + tag)
                pairs.append((l1_, nt_))
                break
    return pairs


def aimed_fetch(t, nt, ink, iy_ink, ix_ink):
    """P._fetch_tile with the crop aimed at (iy_ink, ix_ink) on the ink grid,
    cached under t['seg']. Mirrors pack's format so load_tile serves it."""
    p = P._cache_path(t["seg"])
    if os.path.exists(p):
        return P.load_tile(t)
    try:
        za = json.loads(P.get(f"{P.B}/{t['sv']}0/.zarray", 60).decode())
        D_, HH, WW = za["shape"]
        if za["chunks"][1] != CH:
            return None
        ds = WW / ink.shape[1]
        cy0 = max(0, min(HH // CH - nt, int(round(iy_ink * ds / CH))))
        cx0 = max(0, min(WW // CH - nt, int(round(ix_ink * ds / CH))))
        vol = np.zeros((D_, nt * CH, nt * CH), np.float32)
        got = 0

        def g(cy, cx):
            try:
                b = P.get(f"{P.B}/{t['sv']}0/0/{cy}/{cx}")
                return cy, cx, (np.frombuffer(b, np.uint8).reshape(D_, CH, CH)
                                if len(b) == D_ * CH * CH else None)
            except Exception:
                return cy, cx, None

        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for cy, cx, a in ex.map(lambda q: g(*q),
                                    [(cy0 + j, cx0 + i)
                                     for j in range(nt) for i in range(nt)]):
                if a is not None:
                    got += 1
                    vol[:, (cy - cy0) * CH:(cy - cy0 + 1) * CH,
                        (cx - cx0) * CH:(cx - cx0 + 1) * CH] = a
        if got < nt * nt * 0.5:
            return None
        prof = vol.mean(axis=(1, 2))
        res = dict(vol=vol, pk=int(prof.argmax()), ink=ink, ds=ds,
                   iy=int(cy0 * CH / ds), ix=int(cx0 * CH / ds),
                   um=float(P.true_um(t) or t["um"]),
                   scroll=t["scroll"], seg=t["seg"])
        np.savez(p, vol=res["vol"].astype(np.uint8), pk=res["pk"],
                 ink=res["ink"].astype(np.uint8), ds=res["ds"],
                 iy=res["iy"], ix=res["ix"], um=res["um"])
        return P.load_tile(t)
    except Exception:
        return None


def aim(t_l1, nt_l1=2):
    """Ink-densest window centre, in ink-map coordinates, for an nt_l1-chunk
    window at L1 scale (same physical size as nt=4 native)."""
    try:
        ink = np.array(Image.open(io.BytesIO(
            P.get(f"{P.B}/{t_l1['ink']}")))).astype(np.float32)
        if ink.ndim == 3:
            ink = ink.mean(2)
        za = json.loads(P.get(f"{P.B}/{t_l1['sv']}0/.zarray", 60).decode())
        _, HH, WW = za["shape"]
        ds = WW / ink.shape[1]
        w = max(4, int(round(nt_l1 * CH / ds)))       # window in ink px
        m = (ink > 128).astype(np.float32)
        cs = m.cumsum(0).cumsum(1)
        H, W = m.shape
        if H <= w or W <= w:
            return None, None, None
        s = cs[w:, w:] - cs[:-w, w:] - cs[w:, :-w] + cs[:-w, :-w]
        c = s / float(w * w)
        # A window smaller than a letter aimed at MAX ink lands inside a
        # stroke: cov=1.0, no blank pixels, nothing to rank (measured — every
        # window of the first aimed run scored cov 1.0 and was gated). Aim for
        # a MIXED window instead: closest to 40% ink, so strokes and gaps
        # both exist inside it.
        c[c < 0.08] = np.inf
        score = np.abs(c - float(os.environ.get("INK_AIM", "0.40")))
        iy, ix = np.unravel_index(int(score.argmin()), score.shape)
        if not np.isfinite(score[iy, ix]):
            return None, None, None
        return ink, int(iy), int(ix)
    except Exception:
        return None, None, None


def main():
    pairs = discover()
    print(f"{len(pairs)} segments with a native sibling", flush=True)
    if "--discover" in sys.argv:
        return
    rows = {f: {"native": [], "l1": []} for f in FEATURES}
    paired = 0
    for i, (t_l1, t_nat) in enumerate(pairs):
        ink, iy, ix = aim(t_l1)
        if ink is None:
            print(f"  [{i}] {t_l1['scroll']} no ink-dense window", flush=True)
            continue
        tiles = {"l1": aimed_fetch(t_l1, 2, ink, iy, ix),
                 "native": aimed_fetch(t_nat, 4, ink, iy, ix)}
        if tiles["l1"] is None or tiles["native"] is None:
            print(f"  [{i}] {t_l1['scroll']} fetch "
                  f"(l1={'ok' if tiles['l1'] else 'MISS'}, "
                  f"nat={'ok' if tiles['native'] else 'MISS'})", flush=True)
            continue
        if tiles["native"]["um"] > 1.5:
            print(f"  [{i}] native um={tiles['native']['um']:.3f} — skip", flush=True)
            continue
        paired += 1
        print(f"  [{i}] {t_l1['scroll']} paired at ink window ({iy},{ix})", flush=True)
        for f in FEATURES:
            for d in range(N_DRAWS):
                rng = np.random.default_rng(1000 + d)
                V = D.sample_variant(rng)
                V["features"], V["weights"] = [f], [1.0]
                for side in ("native", "l1"):
                    try:
                        fm = D.feature_map(tiles[side], V)
                    except Exception:
                        fm = None
                    if fm is None:
                        continue
                    r = P.auc_vs_ink(fm, tiles[side])
                    if r is not None and r["null_median"] is not None:
                        rows[f][side].append(
                            dict(seg=t_l1["seg"], scroll=t_l1["scroll"], draw=d,
                                 auc=r["auc"], excess=r["auc"] - r["null_median"],
                                 p=r["p"], cov=r["cov"]))
        P._mem.clear()

    summary = {}
    print(f"\npaired segments scored: {paired}")
    print(f"{'feature':14s} {'n':>3s} {'segs':>4s} {'L1 excess':>10s} "
          f"{'native excess':>14s} {'delta':>8s} {'sig(nat)':>9s}")
    print("-" * 70)
    for f in FEATURES:
        nat, l1 = rows[f]["native"], rows[f]["l1"]
        common = ({x["seg"] for x in nat} & {x["seg"] for x in l1})
        nat = [x for x in nat if x["seg"] in common]
        l1 = [x for x in l1 if x["seg"] in common]
        if len(common) < 2:
            print(f"{f:14s} {len(nat):3d} {len(common):4d} {'--':>10s}")
            summary[f] = dict(n=len(nat), segs=len(common))
            continue
        me_n = float(np.median([x["excess"] for x in nat]))
        me_l = float(np.median([x["excess"] for x in l1]))
        sig = sum(1 for x in nat if x["p"] < 0.05)
        summary[f] = dict(n=len(nat), segs=len(common),
                          scrolls=len({x["scroll"] for x in nat}),
                          excess_native=me_n, excess_l1=me_l, delta=me_n - me_l,
                          sig_native=f"{sig}/{len(nat)}")
        print(f"{f:14s} {len(nat):3d} {len(common):4d} {me_l:+10.3f} "
              f"{me_n:+14.3f} {me_n-me_l:+8.3f} {sig:>4d}/{len(nat)}")
    with open(OUT, "w") as fh:
        json.dump(dict(summary=summary, detail=rows, paired=paired,
                       t=time.strftime("%F %T")), fh, indent=1)
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
