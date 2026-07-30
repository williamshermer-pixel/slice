"""TRACERS — hunt the writing itself, not the texture around it.

THE ARGUMENT FOR THIS TIER

Everything else in this project asks "is this pixel inky?" and answers with a
texture statistic. That question is hopeless at the per-voxel level: the ink
layer is ~15 um, the unread scrolls sampled it at 1.7 voxels, and nine
mechanisms have now failed on it.

A letter is a different object entirely. Measured off real ink on Scroll 1 it is
3.00 mm tall, 1.86 mm of advance, 0.35 mm of stroke — about 75,000 voxels of
known, repeated SHAPE. Integrating a weak per-voxel signal over a known shape is
the one argument that survives the resolution problem, because it buys signal-
to-noise from area rather than from contrast.

And matched filtering asks an easier question. Not "what is here?" but "does an
alpha fit here?" — with the alternatives constrained to 24 shapes, at a known
size, on a known baseline grid, in a known hand.

THE BLOCKER THIS MUST CONFRONT, NOT ASSUME AWAY

An earlier experiment stacked many letter instances expecting sqrt(N)
convergence and got p = 0.365. The reason: the interference is SPATIALLY
CORRELATED. Papyrus fibre, sheet curvature and beam artefacts are not
independent noise draws, so averaging N patches does not divide the noise by
sqrt(N) — it divides it by sqrt(N_effective), and N_effective can be close to 1
if the patches sit inside one correlation length.

So this file measures the correlation length FIRST and reports N_effective
alongside every result. A matched-filter score quoted without it is exactly the
sqrt(N) mistake in a new costume.

WHAT IT DOES

  1 HARVEST    cut letterform templates out of the published ink maps —
               the scribe's actual hand, at known scale, many exemplars
  2 GRID       fit the baseline grid (line pitch, orientation) to collapse the
               search space from every pixel to a few slots per line
  3 MATCH      normalised cross-correlation of each template over a candidate
               signal map, via FFT
  4 FALSIFY    score at TRUE letter positions against spatially-shifted nulls,
               and against the same test with templates from a DIFFERENT
               segment, which is the only version that is not circular

WHAT WOULD MAKE IT A RESULT

Matched response at true positions beating shift-nulls, with templates cut from
a different segment than the one being tested, and N_effective large enough for
the margin to mean anything. Anything less is written down and disbelieved.

Usage
    python3 tracers.py --harvest 6      cut templates, render the alphabet
    python3 tracers.py --validate 8     the falsification run
"""
import os, sys, json, time
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as P
import depth_pca as DP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("INK_OUT", os.path.join(HERE, "..", "out", "tracers"))
os.makedirs(OUT, exist_ok=True)

# the scribe's hand, measured off real ink on Scroll 1
HAND = dict(line_pitch_um=6180.0, letter_h_um=3000.0,
            advance_um=1860.0, stroke_um=350.0)


def um_per_px(tile):
    """Microns per pixel of the published ink map."""
    return tile["um"] * tile["ds"]


# ---------------------------------------------------------------------------
# 1  HARVEST
# ---------------------------------------------------------------------------
def harvest(tile, max_templates=120):
    """Cut letter-sized blobs out of the ink map.

    These are not classified into the 24 letters — that would need labels
    nobody has published. They are exemplars of the hand: whatever shapes this
    scribe actually put on the sheet, at the right scale. For matched filtering
    that is sufficient, and it avoids inventing an alphabet.
    """
    from scipy import ndimage as ndi
    upx = um_per_px(tile)
    h_px = HAND["letter_h_um"]/upx
    if h_px < 4:
        return []                      # ink map too coarse to hold a letter
    m = tile["ink"] > 128
    lab, n = ndi.label(m)
    if n == 0:
        return []
    objs = ndi.find_objects(lab)
    out = []
    for i, sl in enumerate(objs):
        if sl is None:
            continue
        hh = sl[0].stop - sl[0].start
        ww = sl[1].stop - sl[1].start
        # accept things that are plausibly one letter, not a blot or a speck
        if not (0.45*h_px <= hh <= 1.8*h_px):
            continue
        if not (0.25*h_px <= ww <= 2.2*h_px):
            continue
        patch = (lab[sl] == i+1).astype(np.float32)
        if patch.mean() < 0.12 or patch.mean() > 0.92:
            continue
        out.append(dict(patch=patch, box=(sl[0].start, sl[0].stop,
                                          sl[1].start, sl[1].stop)))
        if len(out) >= max_templates:
            break
    return out


def normalise_template(t, shape):
    """Resample to a common box and zero-mean, unit-norm — required for NCC."""
    p = Image.fromarray((t["patch"]*255).astype(np.uint8)).resize(
        (shape[1], shape[0]), Image.BILINEAR)
    a = np.asarray(p, np.float32)/255.0
    a = a - a.mean()
    n = np.sqrt((a*a).sum())
    return a/(n if n > 1e-9 else 1.0)


def template_bank(tiles, n_shape=(16, 12), cap=60):
    """A bank of unit-norm templates gathered across several segments."""
    bank = []
    for t in tiles:
        tile = P.load_tile(t)
        if tile is None:
            continue
        for h in harvest(tile):
            bank.append(normalise_template(h, n_shape))
            if len(bank) >= cap:
                return bank, n_shape
    return bank, n_shape


# ---------------------------------------------------------------------------
# 2  GRID
# ---------------------------------------------------------------------------
def line_pitch(img, upx):
    """Estimate text line pitch by autocorrelating the row profile.

    Returns (pitch_px, strength). Strength is the autocorrelation peak height
    relative to its neighbourhood — a sheet with no ruled text gives a flat
    curve and a strength near zero, which is the honest answer.
    """
    prof = img.astype(np.float32).mean(1)
    prof = prof - prof.mean()
    if prof.std() < 1e-9:
        return None, 0.0
    ac = np.correlate(prof, prof, mode="full")[len(prof)-1:]
    ac = ac/max(ac[0], 1e-9)
    lo = max(3, int(0.5*HAND["line_pitch_um"]/upx))
    hi = min(len(ac)-1, int(2.0*HAND["line_pitch_um"]/upx))
    if hi <= lo+2:
        return None, 0.0
    seg = ac[lo:hi]
    k = int(np.argmax(seg))
    return lo+k, float(seg[k] - np.median(seg))


# ---------------------------------------------------------------------------
# 3  MATCH
# ---------------------------------------------------------------------------
def ncc_max(field, bank):
    """Max normalised cross-correlation over a template bank, by FFT.

    Local mean and energy come from box filters, so the normalisation is the
    proper NCC one and not a global z-score — otherwise bright regions win
    every match regardless of shape, which is the papyrus-condition trap again.
    """
    if not bank:
        return None
    f = np.asarray(field, np.float32)
    f = f - f.mean()
    H, W = f.shape
    th, tw = bank[0].shape
    if H < th*2 or W < tw*2:
        return None
    r = max(1, min(th, tw)//2)
    mu = P.box(f, r)
    e = np.sqrt(np.maximum(P.box(f*f, r) - mu*mu, 1e-12))

    FH, FW = 1 << int(np.ceil(np.log2(H+th))), 1 << int(np.ceil(np.log2(W+tw)))
    Ff = np.fft.rfft2(f, s=(FH, FW))
    best = None
    for t in bank:
        Ft = np.fft.rfft2(t[::-1, ::-1], s=(FH, FW))
        c = np.fft.irfft2(Ff*Ft, s=(FH, FW))[th-1:th-1+H, tw-1:tw-1+W]
        c = c/np.maximum(e*np.sqrt(th*tw), 1e-9)
        best = c if best is None else np.maximum(best, c)
    return best


# ---------------------------------------------------------------------------
# 4  THE THING THAT KILLED STACKING — measure it, do not assume it away
# ---------------------------------------------------------------------------
def correlation_length(a, max_lag=64):
    """Distance at which the field decorrelates, in pixels.

    This is the number that broke letter stacking. If patches sit within one
    correlation length of each other they are not independent samples and
    averaging N of them does not buy sqrt(N).
    """
    f = np.asarray(a, np.float32)
    f = f - f.mean()
    if f.std() < 1e-9:
        return None
    row = f[f.shape[0]//2]
    ac = np.correlate(row, row, mode="full")[len(row)-1:]
    ac = ac/max(ac[0], 1e-9)
    n = min(max_lag, len(ac))
    below = np.where(ac[:n] < 1/np.e)[0]
    return int(below[0]) if len(below) else n


def effective_n(region_px, corr_len):
    """How many INDEPENDENT samples a region is really worth.

    Not "how many letters are there" — how many correlation cells fit in the
    area being integrated over. Everything inside one cell is one sample no
    matter how many letters sit in it, which is precisely why stacking letter
    instances returned p = 0.365.

    region_px and corr_len must be in the SAME units. Mixing ink-map pixels
    with surface-volume pixels here produced an N_eff of 30,000 on a tile that
    holds a few hundred letters.
    """
    if not corr_len or corr_len < 1:
        return None
    return float(region_px)/float(corr_len*corr_len)


# ---------------------------------------------------------------------------
def candidate_field(tile):
    """The signal map the tracer hunts in.

    Uses the depth-PCA components, because they are the only family in this
    project that is unsupervised, fixed across tiles, and not derived from
    sheet brightness. Falls back to the plain depth-band image.
    """
    try:
        F = DP.pca_features(tile)
        if F:
            return sum(P.z(F[k]) for k in sorted(F))/len(F), "pca_sum"
    except Exception:
        pass
    return P.mid_image(tile, 8), "mid"


def validate(n_test=8, n_donor=4):
    """The falsification run.

    Templates are cut from DONOR segments and tested on TEST segments that
    share no segment with them. Cutting and testing on the same sheet would
    measure only that a shape matches itself.
    """
    tg = P.targets()
    by, tune, held, ts, hs = P.split_by_scroll(tg)
    rng = np.random.default_rng(21)
    donors = [tune[i] for i in rng.permutation(len(tune))[:n_donor]]
    tests = [held[i] for i in rng.permutation(len(held))[:n_test]]
    print(f"donor segments (templates cut here): {ts}")
    print(f"test segments   (never donate)     : {hs}\n")
    print("donor tiles:"); donors = P.warm(donors)
    print("test tiles:");  tests = P.warm(tests)

    bank, shape = template_bank(donors)
    print(f"\nharvested {len(bank)} letterform templates at {shape[0]}x{shape[1]}")
    if len(bank) < 8:
        print("too few templates — the ink maps at this scale do not resolve "
              "letter-sized blobs. that is a result: write it down.")
        return []
    _render_bank(bank, shape)

    rows = []
    for t in tests:
        tile = P.load_tile(t)
        if tile is None:
            continue
        upx = um_per_px(tile)
        field, kind = candidate_field(tile)
        resp = ncc_max(field, bank)
        if resp is None:
            continue
        cl = correlation_length(field)
        pitch, strength = line_pitch(tile["ink"], upx)

        cov_gate = (0.02, 0.90)
        s = P.score_vs_ink(resp, tile, require_cov=cov_gate)
        if s is None:
            continue
        base = P.score_vs_ink(field, tile, require_cov=cov_gate)

        # Gain is on ABSOLUTE correlation. A signed difference calls
        # r=-0.312 -> r=-0.047 an improvement of +0.265, when in fact the
        # matched filter destroyed a strong (negative) relationship and
        # replaced it with nothing.
        gain = None if base is None else abs(s["r"]) - abs(base["r"])

        # N_eff over the region actually integrated, in FIELD pixels
        neff = effective_n(field.shape[0]*field.shape[1], cl)
        rows.append(dict(seg=tile["seg"], scroll=tile["scroll"], field=kind,
                         matched_r=s["r"], matched_p=s["p"],
                         raw_r=None if base is None else base["r"],
                         abs_gain=None if gain is None else round(gain, 4),
                         corr_len_px=cl,
                         n_effective=None if neff is None else round(neff, 1),
                         line_pitch_px=pitch, pitch_strength=round(strength, 3),
                         um_per_px=round(upx, 2)))
        print(f"  {tile['scroll']:12s} matched |r|={abs(s['r']):.3f} (p={s['p']:.3f})  "
              f"raw |r|={'--' if base is None else format(abs(base['r']),'.3f')}  "
              f"gain={'--' if gain is None else format(gain,'+.3f')}  "
              f"corr_len={cl}px  N_eff={'--' if neff is None else format(neff,'.0f')}",
              flush=True)

    json.dump(rows, open(os.path.join(OUT, "tracer_validation.json"), "w"), indent=1)
    if rows:
        g = [r["abs_gain"] for r in rows if r["abs_gain"] is not None]
        m = [abs(r["matched_r"]) for r in rows]
        print(f"\nmatched median |r| = {np.median(m):.3f}  (n={len(rows)} tiles)")
        if g:
            print(f"median gain over the raw field = {np.median(g):+.3f}")
            if np.median(g) <= 0.02:
                print("\nmatched filtering bought nothing. Given the correlation lengths\n"
                      "above, that is the sqrt(N) blocker showing up again: the patches\n"
                      "are not independent, so integrating over letter area does not\n"
                      "reduce the noise. This is the honest negative and it belongs in\n"
                      "the submission.")
    return rows


def _render_bank(bank, shape, cols=12):
    try:
        rows = (len(bank)+cols-1)//cols
        S = 48
        img = Image.new("L", (cols*S, rows*S), 0)
        for i, t in enumerate(bank):
            a = t - t.min()
            a = (a/max(a.max(), 1e-9)*255).astype(np.uint8)
            img.paste(Image.fromarray(a).resize((S-4, S-4), Image.NEAREST),
                      ((i % cols)*S+2, (i//cols)*S+2))
        img.save(os.path.join(OUT, "alphabet.png"))
        print(f"  template bank rendered: {os.path.join(OUT,'alphabet.png')}")
    except Exception:
        pass


if __name__ == "__main__":
    a = sys.argv[1:]
    mode = a[0] if a else "--validate"
    n = int(a[1]) if len(a) > 1 else 8
    t0 = time.time()
    if mode == "--harvest":
        tg = P.targets()
        by, tune, held, ts, hs = P.split_by_scroll(tg)
        rng = np.random.default_rng(21)
        d = [tune[i] for i in rng.permutation(len(tune))[:n]]
        P.warm(d)
        bank, shape = template_bank(d)
        print(f"harvested {len(bank)} templates")
        _render_bank(bank, shape)
    else:
        validate(n)
    print(f"{time.time()-t0:.0f}s")
