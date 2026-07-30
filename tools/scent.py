"""SCENT — what to tell the dogs to smell for.

The dogs are only as good as the features they can search. Until now the bank
was 19 features and every single one measures a LEVEL: density, brightness,
relief height, local variance, orientation coherence, PCA projections. The
research in `findings/ink-physics.md` says the ink is not a level:

  1 the working X-ray mechanism is PHASE CONTRAST — "the carbon black ink does
    not completely penetrate the fibres, causing the X-rays to undergo a minimum
    deviation at that point", i.e. an EDGE effect at the ink/fibre boundary
  2 the ink carries LEAD at 84 ug/cm2, ~0.5% by volume, which given the absent
    density signal must be PARTICULATE — an upper-tail phenomenon
  3 the ink WETS the fibres and fills inter-fibre voids, so inked regions should
    be LESS POROUS — a lower-tail phenomenon
  4 the visible signature is a "crackle ... raised slightly above the papyrus",
    i.e. strokes are RAISED BARS of a known width

A box filter averages 1, 2 and 3 into nothing. That is a structural blind spot,
not bad luck, and it is the single best explanation for fourteen negatives.

So this module adds five features built on the physics rather than on generic
texture statistics:

  ridge       Hessian ridge response at STROKE WIDTH. A letter stroke is a bar
              0.35 mm wide; this is a matched filter for a bar of that width,
              and it is signed, so bright strokes and dark strokes separate.
  fringe      Laplacian energy at fine scale — the antisymmetric bright/dark
              doublet phase contrast produces at a boundary. Levels cannot see
              this; a second derivative can.
  specks      density of extreme-BRIGHT voxels (candidate lead grains)
  voids       density of extreme-DARK voxels (porosity; ink should reduce it)
  speckdepth  how tightly the bright specks cluster at the sheet FACE.
              Ink was applied to a surface. Mineral grit has no reason to
              prefer one depth. This one uses no labels at all.

All scales are in microns so they transfer between a 1.13 um scan and a 7.9 um
one.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

# the scribe's hand, measured off real ink on Scroll 1
STROKE_UM = 350.0

DEFAULT = dict(
    stroke_um=STROKE_UM,
    fringe_um=40.0,        # fine scale for the edge doublet
    band=8,                # depth layers each side of the sheet peak
    tail_pct=99.5,         # bright-tail threshold
    void_pct=2.0,          # dark-tail threshold
    tail_band=20,
    offset=0,              # depth offset from the sheet peak
)


def _smooth(a, um, scale_um):
    """Two box passes approximate a Gaussian well enough and stay O(n)."""
    r = max(1, int(round(scale_um/um/2)))
    return P.box(P.box(a, r), r)


def ridge(img, um, stroke_um):
    """Hessian ridge response matched to a bar of width `stroke_um`.

    A letter stroke is a raised bar of known width, not a blob and not an edge.
    The Hessian eigenvalues separate bar-like structure (one large eigenvalue,
    one small) from blobs (both large) and from flat noise (both small), which
    no isotropic gradient statistic can do.

    Signed: positive for bright ridges, negative for dark ones, so the search
    does not have to guess the polarity of the ink.
    """
    s = _smooth(img, um, stroke_um)
    gy, gx = np.gradient(s)
    Hyy, Hyx = np.gradient(gy)
    Hxy, Hxx = np.gradient(gx)
    tr = Hxx + Hyy
    det = Hxx*Hyy - 0.25*(Hxy+Hyx)**2
    disc = np.sqrt(np.maximum(tr*tr/4.0 - det, 0.0))
    l1 = tr/2.0 + disc          # larger magnitude eigenvalue (signed)
    l2 = tr/2.0 - disc
    big = np.where(np.abs(l1) >= np.abs(l2), l1, l2)
    small = np.where(np.abs(l1) >= np.abs(l2), l2, l1)
    # bar-ness: one strong curvature, one weak
    aniso = 1.0 - np.abs(small)/np.maximum(np.abs(big), 1e-9)
    return -big*aniso           # sign flip so bright bars read positive


def fringe(img, um, fringe_um):
    """Edge-doublet energy — the phase-contrast signature.

    Propagation-based phase contrast renders a boundary as an antisymmetric
    bright/dark pair rather than a step. Its second derivative is large and
    changes sign across the edge; its MEAN is ~zero, which is exactly why every
    averaging measure in this project is blind to it.
    """
    s = _smooth(img, um, fringe_um)
    gy, gx = np.gradient(s)
    lap = np.gradient(gy, axis=0) + np.gradient(gx, axis=1)
    r = max(1, int(round(fringe_um/um)))
    return np.sqrt(np.maximum(P.box(lap*lap, r), 0.0))


def _tail_maps(tile, p):
    """Bright- and dark-tail voxel counts per column, plus the bright-tail
    depth profile. One pass, because reading the band is the expensive part."""
    pk = tile["pk"] + int(p.get("offset", 0))
    b = int(p["tail_band"])
    v = P.layers(tile, pk-b, pk+b+1)
    if v.size == 0:
        return None, None, None
    solid = v[v > 0]
    if solid.size < 1000:
        return None, None, None
    hi = float(np.percentile(solid, p["tail_pct"]))
    lo = float(np.percentile(solid, p["void_pct"]))
    hot = (v >= hi) & (v > 0)
    cold = (v <= lo) & (v > 0)
    return (hot.sum(0).astype(np.float32),
            cold.sum(0).astype(np.float32),
            hot.sum(axis=(1, 2)).astype(np.float32))


def speck_depth_map(tile, p):
    """Local concentration of bright specks toward the sheet face.

    For each column, the fraction of its specks lying in the central third of
    the depth band. Ink sits on a surface; grit does not care. This is the one
    feature here that references no ink label, directly or indirectly.
    """
    pk = tile["pk"] + int(p.get("offset", 0))
    b = int(p["tail_band"])
    v = P.layers(tile, pk-b, pk+b+1)
    if v.size == 0:
        return None
    solid = v[v > 0]
    if solid.size < 1000:
        return None
    hi = float(np.percentile(solid, p["tail_pct"]))
    hot = (v >= hi) & (v > 0)
    n = hot.shape[0]
    c = n//2
    core = hot[max(0, c-n//6):c+n//6+1].sum(0).astype(np.float32)
    tot = hot.sum(0).astype(np.float32)
    return core/np.maximum(tot, 1.0)


def scent_features(tile, p=None):
    """The physics-grounded bank, ready for the dogs."""
    p = dict(DEFAULT, **(p or {}))
    um = tile["um"]
    img = P.mid_image(tile, int(p["band"]), int(p.get("offset", 0)))
    if (img > 0).mean() < 0.5:
        return {}
    F = {}
    F["ridge"] = ridge(img, um, float(p["stroke_um"]))
    F["fringe"] = fringe(img, um, float(p["fringe_um"]))
    hot, cold, _ = _tail_maps(tile, p)
    if hot is not None:
        F["specks"] = hot
        F["voids"] = cold
    sd = speck_depth_map(tile, p)
    if sd is not None:
        F["speckdepth"] = sd
    return F


SCENT_NAMES = ["ridge", "fringe", "specks", "voids", "speckdepth"]
