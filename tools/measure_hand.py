"""MEASURE A SCRIBE'S HAND from published ink maps — the gate that every
search must be calibrated to, and the one this project has been burned by.

Applying Scroll 1's 3.0 mm ruler to PHerc0139 (1.09 mm) manufactured
candidates that had to be retracted. Before any scroll is searched, its own
hand is measured here: letter height from connected components of the
published calls, line pitch from row-projection autocorrelation.

  python3 tools/measure_hand.py PHerc0500P2 [PHerc0343P ...]

Prints a HANDS-table row ready to paste into tools/differential_0139.py.
"""
import io, json, os, sys
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
MAX_SEGS = 6


def fetch(u, t=180):
    import urllib.request
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=t).read()


def comps_of(mask, min_area=12):
    """Connected components via iterative flood fill on a downsampled mask."""
    lab = np.zeros(mask.shape, np.int32)
    out = []
    cur = 0
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys, xs):
        if lab[sy, sx]:
            continue
        cur += 1
        st = [(sy, sx)]
        lab[sy, sx] = cur
        pts = []
        while st:
            y, x = st.pop()
            pts.append((y, x))
            for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if (0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1]
                        and mask[ny, nx] and not lab[ny, nx]):
                    lab[ny, nx] = cur
                    st.append((ny, nx))
        if len(pts) >= min_area:
            yy = [p[0] for p in pts]; xx = [p[1] for p in pts]
            out.append((max(yy)-min(yy)+1, max(xx)-min(xx)+1, len(pts)))
    return out


def band_height(mask, pitch_px, um_px):
    """Letter height from the VERTICAL EXTENT of each text band.

    Connected components CANNOT measure letter height here: the published maps
    are binarized, so a letter fragments into separate strokes and the median
    component is a fragment (validated against Scroll 1: components said
    0.58 mm, the true hand is 3.00 mm). The ink band of a text line, however,
    is the letter height by definition. Fold the mask on the measured line
    pitch and take the width of the folded profile at half maximum.
    """
    if not pitch_px or pitch_px < 4:
        return None
    proj = mask.sum(1).astype(np.float32)
    n = int(pitch_px)
    k = len(proj) // n
    if k < 2:
        return None
    folded = proj[:k * n].reshape(k, n).mean(0)
    folded -= folded.min()
    if folded.max() < 1e-6:
        return None
    folded /= folded.max()
    # width at half maximum, measured circularly around the peak
    pk = int(np.argmax(folded))
    rolled = np.roll(folded, n // 2 - pk)
    above = np.nonzero(rolled >= 0.5)[0]
    if above.size == 0:
        return None
    return float((above.max() - above.min() + 1) * um_px / 1000.0)


def line_pitch(mask, um_px):
    """Row-projection autocorrelation peak = spacing between text lines."""
    proj = mask.sum(1).astype(np.float32)
    proj -= proj.mean()
    if proj.std() < 1e-6:
        return None
    ac = np.correlate(proj, proj, "full")[len(proj)-1:]
    ac /= max(ac[0], 1e-9)
    lo = max(3, int(1500 / um_px))            # ignore <1.5 mm
    hi = min(len(ac)-1, int(15000 / um_px))   # ignore >15 mm
    if hi <= lo:
        return None
    return float((lo + int(np.argmax(ac[lo:hi]))) * um_px / 1000.0)


def measure(scroll):
    targets = [t for t in json.load(
        open(os.path.join(ROOT, "findings", "targets.json")))
        if t["scroll"] == scroll]
    if not targets:
        print(f"{scroll}: no targets")
        return None
    heights, pitches = [], []
    used = 0
    for t in targets:
        if used >= MAX_SEGS:
            break
        try:
            a = np.array(Image.open(io.BytesIO(fetch(f"{B}/{t['ink']}")))
                         ).astype(np.float32)
        except Exception as e:
            print(f"  {t['seg'].split('/')[-2][:22]}: fetch failed ({e})")
            continue
        if a.ndim == 3:
            a = a.mean(2)
        m = a > 128
        if m.mean() < 0.005:
            continue
        used += 1
        # published maps are ds8 of the -L1 canvas -> um per jpeg px
        um_px = t["um"] * 8.0
        # work on a crop for speed: the densest 1200x1200 region
        H, W = m.shape
        s = 1200
        if H > s and W > s:
            rs = m[::8, ::8].astype(np.float32)
            k = max(1, s // 8)
            cs = rs.cumsum(0).cumsum(1)
            if cs.shape[0] > k and cs.shape[1] > k:
                bx = (cs[k:, k:] - cs[:-k, k:] - cs[k:, :-k] + cs[:-k, :-k])
                iy, ix = np.unravel_index(int(bx.argmax()), bx.shape)
                m = m[iy*8:iy*8+s, ix*8:ix*8+s]
        p = line_pitch(m, um_px)
        if p:
            pitches.append(p)
            bh = band_height(m, p * 1000.0 / um_px, um_px)
            if bh and 0.2 < bh < 12.0:
                heights.append(bh)
    if not heights:
        print(f"{scroll}: no measurable components")
        return None
    h = np.array(heights)
    med = float(np.median(h))
    p25, p75 = float(np.percentile(h, 25)), float(np.percentile(h, 75))
    if len(h) < 2:
        p25, p75 = med * 0.8, med * 1.3
    pitch = float(np.median(pitches)) if pitches else med * 2.2
    print(f"\n{scroll}: {used} segments, {len(h)} text bands measured")
    print(f"  letter height  {med:.2f} mm  (band FWHM; p25 {p25:.2f} / p75 {p75:.2f})")
    print(f"  line pitch     {pitch:.2f} mm" +
          ("" if pitches else "  [estimated, no autocorrelation peak]"))
    lo, hi = max(0.3, p25 * 0.7), p75 * 1.5
    adv = med * 0.64          # advance/height ratio measured on Scroll 1
    mode = "shape" if med >= 2.0 else "envelope"
    print(f'  HANDS row -> "{scroll}": ("{scroll.lower()}", {med:.2f}, '
          f'{lo:.2f}, {hi:.2f}, {adv:.2f}, {pitch:.2f}, "{mode}"),')
    print(f"  mode {mode}: the model emits 0.29 mm blocks, so a {med:.2f} mm "
          f"hand is {'resolvable as shape' if mode=='shape' else 'mass-only'}")
    return dict(scroll=scroll, letter_mm=round(med, 2), lo=round(lo, 2),
                hi=round(hi, 2), advance_mm=round(adv, 2),
                pitch_mm=round(pitch, 2), mode=mode, n=len(h), segs=used)


if __name__ == "__main__":
    names = sys.argv[1:] or ["PHerc0500P2", "PHerc0343P", "PHerc0814"]
    rows = [r for r in (measure(s) for s in names) if r]
    out = os.path.join(ROOT, "findings", "hands.json")
    prev = json.load(open(out)) if os.path.exists(out) else {}
    prev.update({r["scroll"]: r for r in rows})
    json.dump(prev, open(out, "w"), indent=1)
    print(f"\n-> findings/hands.json ({len(prev)} scribes measured)")
