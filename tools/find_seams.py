#!/usr/bin/env python3
"""Find segments that meet EDGE TO EDGE, so a word split by the seam can be rejoined.

THE IDEA, which is William's. Segmentation carves one sheet of papyrus into
patches. A patch boundary is an arbitrary line drawn by a mesh algorithm, not
by the scribe -- so words sit astride it, half on one segment and half on the
next. Every ink search in this project deliberately excluded segment edges
(keep-out zones to avoid model spillover), which means the split words are the
one place systematically NOT looked at.

This is NOT the wrap-stacking case. Consecutive windings of a roll are a full
turn apart and carry different columns; that was tested in
tools/sandwich_0343p.py and came back empty. This is patches side by side on
the SAME sheet surface, where the text really is continuous across the join.

HOW ADJACENCY IS DECIDED. Every segment of a scroll carries a tifxyz mesh in a
common reference frame -- for Scroll 1, all 80 are meshed against the 45.532 um
volume -- so each flattened cell has a known 3D position in one shared space.
Two patches are edge-adjacent when their BOUNDARY cells come close in 3D while
their interiors do not overlap. Interior overlap would mean two segmentations of
the same papyrus (a duplicate), which is a different thing and is reported
separately rather than counted as a seam.

Coarse frame on purpose: 45.532 um voxels are ample for deciding which patches
touch, and the whole scroll is ~25 MB. The fine 2.4 um mesh (34 MB per segment)
is only worth fetching for a pair that already looks joined.

    python3 tools/find_seams.py --scroll PHercParis4
"""
import argparse
import concurrent.futures as cf
import io
import json
import os
import urllib.request

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
UA = {"User-Agent": "Mozilla/5.0"}
CATALOG = os.path.join(ROOT, "public", "ink-maps.json")
OUT = os.path.join(ROOT, "out", "seams")

FRAME = {
    "PHercParis4": "20260310170716-45.532um",
    "PHerc0139": "20250728140407-9.362um",
    "PHerc0343P": "20250521134555-8.64um",
}
VOXEL_UM = {"20260310170716-45.532um": 45.532,
            "20250728140407-9.362um": 9.362,
            "20250521134555-8.64um": 8.64}


def fetch(url, cache, timeout=240):
    os.makedirs(cache, exist_ok=True)
    p = os.path.join(cache, url.replace(B + "/", "").replace("/", "__"))
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return open(p, "rb").read()
    d = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()
    open(p, "wb").write(d)
    return d


def load(scroll, seg, frame, cache):
    import tifffile
    sid = seg[:14]
    base = f"{B}/{scroll}/segments/{seg}/mesh/{sid}-on-{frame}.tifxyz"
    a = [tifffile.imread(io.BytesIO(fetch(f"{base}/{ax}.tif", cache))).astype(np.float32)
         for ax in "xyz"]
    xyz = np.stack(a, -1)
    valid = (xyz != 0).any(-1)
    return xyz, valid


def boundary(valid):
    """Cells on the rim of the patch."""
    er = ndimage.binary_erosion(valid, np.ones((3, 3), bool), border_value=0)
    return valid & ~er


def normals(xyz, valid):
    """Unit surface normal per mesh cell, from the parameterisation's gradients.

    This is what separates a seam from a stacked wrap, and two weaker tests
    failed before it. Proximity alone cannot work: a rolled scroll puts the
    next winding ~150 um away, so at any usable threshold every wrap "touches"
    every other, and the first two runs both returned ~3000 pairs with one
    segment adjacent to the entire scroll.

    Direction is the discriminator. Walk from a rim cell of A to the nearest
    cell of B and decompose that offset against A's local surface normal:

        along the normal   -> B is the next winding, stacked above or below
        in the surface     -> B continues the same sheet, and the join is a
                              seam a word can straddle

    A normal cannot be taken AT a rim cell, which is the trap this walked into
    first. Central differences there straddle the zero-fill outside the patch,
    so du and dv both point from the cell to the origin, come out nearly
    parallel, and their cross product collapses: measured 0 of 694 rim cells on
    Scroll 1 seg 20231005123336 had a usable normal, against 20781 of 22950
    interior cells. Filtering on that silently emptied every rim and the scan
    returned zero pairs.

    So normals are computed on the INTERIOR and then smoothed outward to reach
    the rim. Interior normals agree with their smoothed neighbourhood at 0.972,
    so the field is smooth enough that extending it a cell or two is safe.
    """
    du = np.zeros_like(xyz)
    dv = np.zeros_like(xyz)
    du[:, 1:-1] = xyz[:, 2:] - xyz[:, :-2]
    dv[1:-1, :] = xyz[2:] - xyz[:-2]
    n = np.cross(du, dv)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-6)

    # Keep only trustworthy (interior) normals, then diffuse them outward.
    interior = valid & ~boundary(valid) & (np.linalg.norm(n, axis=-1) > 0.5)
    n[~interior] = 0
    sm = np.stack([ndimage.uniform_filter(n[..., k], 9) for k in range(3)], -1)
    l2 = np.linalg.norm(sm, axis=-1, keepdims=True)
    sm = np.divide(sm, l2, out=np.zeros_like(sm), where=l2 > 1e-6)
    n = np.where(interior[..., None], n, sm)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scroll", default="PHercParis4")
    ap.add_argument("--touch-um", type=float, default=400.0,
                    help="boundary cells this close in 3D count as joined")
    args = ap.parse_args()

    frame = FRAME[args.scroll]
    vox = VOXEL_UM[frame]
    touch_vox = args.touch_um / vox
    cache = os.path.join(OUT, "cache")
    os.makedirs(OUT, exist_ok=True)

    doc = json.load(open(CATALOG))
    segs = sorted({e["segment"] for e in doc["entries"]
                   if e["scroll"] == args.scroll})
    print(f"{args.scroll}: {len(segs)} segments, frame {frame} "
          f"({vox} um/vox), touch <= {args.touch_um} um "
          f"({touch_vox:.1f} vox)\n")

    def one(seg):
        try:
            xyz, valid = load(args.scroll, seg, frame, cache)
        except Exception as e:
            return seg, None, None, None, str(e)
        nrm = normals(xyz, valid)
        rb = boundary(valid)
        # a rim cell is only usable if its normal is well defined
        good = rb & (np.linalg.norm(nrm, axis=-1) > 0.5)
        return seg, xyz[good], nrm[good], xyz[valid], None

    rim, rimn, body = {}, {}, {}
    with cf.ThreadPoolExecutor(10) as ex:
        for seg, r, rn, b, err in ex.map(one, segs):
            if err:
                print(f"  {seg[:34]:36s} SKIP {err[:50]}")
                continue
            rim[seg], rimn[seg], body[seg] = r, rn, b
    print(f"loaded {len(rim)} meshes\n")

    names = sorted(rim)
    bodyT = {s: cKDTree(body[s]) for s in names}
    rimT = {s: cKDTree(rim[s]) for s in names}
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            # cheap bbox reject
            amin, amax = body[a].min(0), body[a].max(0)
            bmin, bmax = body[b].min(0), body[b].max(0)
            if (amin > bmax + touch_vox).any() or (bmin > amax + touch_vox).any():
                continue
            dbody, idx = bodyT[b].query(rim[a],
                                        distance_upper_bound=touch_vox * 6,
                                        workers=-1)
            near = dbody <= touch_vox
            n_near = int(near.sum())
            if n_near < 20:
                continue

            # Decompose the offset to the nearest cell of B against A's local
            # surface normal. |offset . n| is how far B sits ABOVE the sheet
            # (a stacked winding); the in-plane remainder is how far it sits
            # BESIDE it (a seam).
            off = body[b][idx[near]] - rim[a][near]
            n = rimn[a][near]
            perp = np.abs((off * n).sum(-1))
            inplane = np.sqrt(np.maximum(np.einsum("ij,ij->i", off, off)
                                         - perp ** 2, 0.0))
            edge_on = inplane > perp          # beside, not on top of
            n_seam = int(edge_on.sum())
            if n_seam < 20:
                continue

            di, _ = bodyT[b].query(body[a], distance_upper_bound=touch_vox * 6,
                                   workers=-1)
            overlap = float((di <= touch_vox).mean())
            pairs.append(dict(
                a=a, b=b,
                rim_cells_touching=n_seam,
                rim_frac=round(n_seam / max(len(rim[a]), 1), 3),
                edge_on_frac=round(n_seam / max(n_near, 1), 3),
                interior_overlap=round(overlap, 3),
                median_perp_um=round(float(np.median(perp[edge_on]) * vox), 1),
                median_inplane_um=round(float(np.median(inplane[edge_on]) * vox), 1),
                seam_len_mm=round(n_seam * vox / 1000, 1),
                kind="duplicate" if overlap > 0.5 else "seam"))

    pairs.sort(key=lambda p: -p["rim_cells_touching"])
    seams = [p for p in pairs if p["kind"] == "seam"]
    dups = [p for p in pairs if p["kind"] == "duplicate"]
    print(f"{len(seams)} edge-adjacent pairs, {len(dups)} overlapping "
          f"(duplicate segmentations)\n")
    for p in seams[:15]:
        print(f"  {p['a'][:22]:24s} | {p['b'][:22]:24s} "
              f"seam {p['seam_len_mm']:6.1f} mm  "
              f"edge-on {100*p['edge_on_frac']:5.1f}%  "
              f"perp {p['median_perp_um']:6.1f} um  "
              f"in-plane {p['median_inplane_um']:6.1f} um")

    out = dict(scroll=args.scroll, frame=frame, voxel_um=vox,
               touch_um=args.touch_um, segments=len(rim),
               note="Edge-adjacent segment pairs. A seam is where a mesh "
                    "boundary cuts the papyrus, so words can be split across "
                    "it; every ink search here excluded segment edges, making "
                    "these the least-searched text in the library.",
               seams=seams, duplicates=dups)
    p = os.path.join(OUT, f"{args.scroll}.json")
    json.dump(out, open(p, "w"), indent=1)
    print(f"\n-> {p}")


if __name__ == "__main__":
    main()
