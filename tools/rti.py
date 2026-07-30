"""RTI — Reflectance Transformation Imaging, specular-enhancement mode.

WHY THIS AND NOT THE RAKING LIGHT THAT ALREADY FAILED

An earlier attempt in this project shone one light across the sheet and
correlated the result with ink. It scored r = 0.02. The post-mortem said it
"differentiates away the signal it needs", and that is exactly right: a single
raking light is a directional derivative, so a stroke running parallel to the
light vanishes completely. Half the letterform is invisible at any given
azimuth, and a Greek letter has strokes in every direction.

RTI is the standard answer to this on inscriptions, and it is not a better
light — it is a per-pixel reflectance MODEL, sampled from many light angles,
which you then relight or push through a non-physical response curve to make
faint relief legible. Three things here that the raking attempt did not do:

  1 MANY LIGHTS, ACCUMULATED. Sweep azimuth all the way round and keep the
    VARIANCE across lights, not any single frame. A flat patch looks the same
    under every light and scores zero. A stroke of any orientation changes
    under some light and scores. Orientation blindness goes away.

  2 NORMAL UNSHARP. The "enhancement" in specular enhancement. Subtract a
    smoothed copy of the normal field and add the residual back with gain. This
    amplifies small relief against large gentle curvature — which is precisely
    the problem here, where the sheet's own bowing is enormous compared to a
    letter.

  3 BAND-PASS BEFORE NORMALS. The measured noise floor on this data is ~30 um
    against a ~9 um signal. Taking normals of a raw height field is therefore
    taking normals of noise. Band-passing at stroke scale (0.35 mm) before
    differentiating is the difference between a measurement and a random field.

WHAT IT IS NOT

RTI is a DISPLAY technique. It adds no information — it re-encodes relief the
scan already contains into a form an eye, or a correlator, can pick up. If the
relief is not in the data it will not be in the render. That matters here
because the ink layer on the unread scrolls was scanned at 1.7 voxels and was
never sampled at all. On those, this will show nothing, and it should.

It is being tried because the ~15 um ink layer sits ON TOP of the sheet, so it
is a physical bump, and because on the READ scroll the relief is at least
present in principle at 1.13 um/voxel.

Usage
    python3 rti.py --render <n>        relight frames + normal map, n tiles
    python3 rti.py --validate <n>      score across held-out scrolls + control
"""
import os, sys, json, time
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P

OUT = os.environ.get("INK_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "rti"))
os.makedirs(OUT, exist_ok=True)

# defaults tuned to the measured hand: stroke 0.35 mm, letter 3.0 mm
DEFAULT = dict(
    band=10,           # depth layers each side of the sheet peak
    lo_um=150.0,       # band-pass low  — under half a stroke width
    hi_um=1200.0,      # band-pass high — under half a letter height
    unsharp_um=600.0,  # normal-unsharp radius
    gain=3.0,          # normal-unsharp gain
    exponent=40.0,     # Blinn-Phong specular tightness
    elev_deg=18.0,     # light elevation. low = raking
    n_lights=16,       # azimuths swept
)


def normals(tile, p):
    """Enhanced surface normals from the band-passed height field."""
    um = tile["um"]
    h, _ = P.height_map(tile, band=int(p["band"]))
    h = P.bandpass(h, um, p["lo_um"], p["hi_um"])

    # slope is dimensionless: microns of height per micron of travel
    gy, gx = np.gradient(h)
    nx, ny = -gx/um, -gy/um
    nz = np.ones_like(nx)

    # --- normal unsharp: the enhancement step -----------------------------
    r = max(1, int(round(p["unsharp_um"]/um/2)))
    g = float(p["gain"])
    nx = nx + g*(nx - P.box(nx, r))
    ny = ny + g*(ny - P.box(ny, r))

    n = np.sqrt(nx*nx + ny*ny + nz*nz)
    return nx/n, ny/n, nz/n, h


def relight(nx, ny, nz, az_deg, elev_deg, exponent):
    """Blinn-Phong specular under one light. View is straight down."""
    a, e = np.radians(az_deg), np.radians(elev_deg)
    lx, ly, lz = np.cos(e)*np.cos(a), np.cos(e)*np.sin(a), np.sin(e)
    # half-vector between light and view (0,0,1)
    hx, hy, hz = lx, ly, lz + 1.0
    hn = np.sqrt(hx*hx + hy*hy + hz*hz)
    hx, hy, hz = hx/hn, hy/hn, hz/hn
    spec = np.maximum(nx*hx + ny*hy + nz*hz, 0.0)**exponent
    diff = np.maximum(nx*lx + ny*ly + nz*lz, 0.0)
    return spec, diff


def rti_features(tile, p=None):
    """The RTI-derived quantities, as feature maps the pack can search over.

    Every one is accumulated across the full azimuth sweep, so none of them can
    be blind to a stroke's orientation the way single-angle raking was.
    """
    p = dict(DEFAULT, **(p or {}))
    nx, ny, nz, h = normals(tile, p)
    az = np.linspace(0, 360, int(p["n_lights"]), endpoint=False)
    S = np.stack([relight(nx, ny, nz, a, p["elev_deg"], p["exponent"])[0] for a in az])

    F = {}
    F["rti_specvar"] = S.std(0)                 # relief that responds to light angle
    F["rti_specmax"] = S.max(0) - S.mean(0)     # peak response above its own baseline
    F["rti_slope"] = 1.0 - nz                   # how tilted, regardless of direction
    gyx = np.gradient(nx, axis=1)
    gyy = np.gradient(ny, axis=0)
    F["rti_curv"] = -(gyx + gyy)                # ridges positive, hollows negative
    F["rti_height"] = h
    return F


RTI_NAMES = ["rti_specvar", "rti_specmax", "rti_slope", "rti_curv", "rti_height"]


# ---------------------------------------------------------------------------
def n8(a, lo=2, hi=98):
    a = np.asarray(a, np.float32)
    l, h = np.percentile(a, lo), np.percentile(a, hi)
    return np.clip((a-l)/max(h-l, 1e-6)*255, 0, 255).astype(np.uint8)


def render(tiles, p=None):
    """Relight frames, normal map, and every feature beside the ink truth.

    The animated sweep is the part a human should look at: real relief moves
    coherently as the light goes round, noise flickers.
    """
    p = dict(DEFAULT, **(p or {}))
    for t in tiles:
        tile = P.load_tile(t)
        if tile is None:
            continue
        seg = tile["seg"].strip("/").split("/")[-1][:28]
        nx, ny, nz, h = normals(tile, p)

        frames = []
        for a in np.linspace(0, 360, 24, endpoint=False):
            spec, diff = relight(nx, ny, nz, a, p["elev_deg"], p["exponent"])
            img = 0.35*diff + 0.65*spec/max(spec.max(), 1e-6)
            frames.append(Image.fromarray(n8(img)).resize((512, 512), Image.LANCZOS))
        gif = os.path.join(OUT, f"{seg}_sweep.gif")
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=90, loop=0)

        nm = np.dstack([n8((nx+1)/2, 1, 99), n8((ny+1)/2, 1, 99), n8(nz, 1, 99)])
        Image.fromarray(nm).resize((512, 512), Image.LANCZOS).save(
            os.path.join(OUT, f"{seg}_normals.png"))

        F = rti_features(tile, p)
        names = ["rti_specvar", "rti_specmax", "rti_curv"]
        S = 380
        sheet = Image.new("L", (S*(len(names)+2)+10*(len(names)+1), S), 0)
        sheet.paste(Image.fromarray(n8(P.mid_image(tile, int(p["band"])))).resize((S, S), Image.LANCZOS), (0, 0))
        for i, nmz in enumerate(names):
            sheet.paste(Image.fromarray(n8(F[nmz])).resize((S, S), Image.LANCZOS),
                        ((i+1)*(S+10), 0))
        ink = np.clip(tile["ink"], 0, 255).astype(np.uint8)
        sheet.paste(Image.fromarray(ink).resize((S, S), Image.LANCZOS),
                    ((len(names)+1)*(S+10), 0))
        sheet.save(os.path.join(OUT, f"{seg}_panel.png"))
        print(f"  {seg}: sweep.gif, normals.png, panel.png  "
              f"[slice | {' | '.join(n.replace('rti_','') for n in names)} | INK]", flush=True)


def validate(n_held=14, p=None):
    """Score every RTI feature on held-out scrolls, then on blank papyrus.

    Reported side by side on purpose. A feature is only interesting if the
    first number is high AND the second is near zero. The first overnight run
    proved that reporting only the first manufactures findings.
    """
    p = dict(DEFAULT, **(p or {}))
    tg = P.targets()
    by, tune, held, ts, hs = P.split_by_scroll(tg)
    print(f"tune scrolls {ts}\nheld-out scrolls {hs}\n")
    rng = np.random.default_rng(11)
    pick = list(rng.choice(held, size=min(n_held, len(held)), replace=False))
    print("held-out tiles:")
    pick = P.warm(pick)
    print("negative-control tiles (blank papyrus):")
    negs = P.find_negatives(held, n=6)
    negs = P.warm(negs)

    rows = []
    for nm in RTI_NAMES:
        rs, ps = [], []
        for t in pick:
            tile = P.load_tile(t)
            if tile is None:
                continue
            try:
                f = rti_features(tile, p)[nm]
            except Exception:
                continue
            s = P.score_vs_ink(f, tile)
            if s:
                rs.append(s["r"]); ps.append(s["p"])
        if len(rs) < 4:
            print(f"  {nm:14s} too few tiles"); continue
        rs = np.array(rs)
        sign = 1.0 if np.median(rs) > 0 else -1.0
        med = float(np.median(sign*rs))
        frac = float((np.array(ps) < 0.05).mean())
        nr = P.neg_control(lambda tl, _n=nm: rti_features(tl, p)[_n], negs)
        fin = P.penalised(med, nr)
        rows.append(dict(feature=nm, heldout_median=med, frac_signif=frac,
                         n=len(rs), negative_control=nr, penalised=fin))
        print(f"  {nm:14s} held-out r={med:+.3f}  {frac*100:3.0f}% signif  n={len(rs):2d}  "
              f"blank |r|={nr if nr is None else round(nr,3)}  ->  penalised {fin:+.3f}",
              flush=True)
    json.dump(rows, open(os.path.join(OUT, "rti_validation.json"), "w"), indent=1)
    print(f"\nwritten {os.path.join(OUT, 'rti_validation.json')}")
    if rows:
        best = max(rows, key=lambda r: r["penalised"])
        print(f"best after penalty: {best['feature']} {best['penalised']:+.3f}")
        if best["penalised"] < 0.15:
            print("nothing here clears a useful bar. that is a result — write it down.")
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    mode = a[0] if a else "--validate"
    n = int(a[1]) if len(a) > 1 else (3 if mode == "--render" else 14)
    t0 = time.time()
    if mode == "--render":
        tg = P.targets()
        by, tune, held, ts, hs = P.split_by_scroll(tg)
        rng = np.random.default_rng(5)
        pick = list(rng.choice(held, size=n, replace=False))
        print("rendering RTI for", n, "tiles")
        P.warm(pick)
        render(pick)
    else:
        validate(n)
    print(f"{time.time()-t0:.0f}s")
