"""MAKE READY-TO-RUN IMAGE/LABEL PAIRS — the deliverable for villa #192.

Read the issue literally. It asks for four things and the first attempt missed
three of them:

  1. "in true 3d rather than a single image projected across multiple layers"
     -> depth comes from SLIDING the model's 62-layer input window through the
        stack (tools/pod_depth_profile.py). Each pixel gets a measured
        response profile p(z); ink is attributed to where that profile peaks.
        NOT one 2D map copied down the band, which is what v1 did.
  2. "Image/label PAIRS"
     -> every crop ships image/ AND label/ together. CC BY-NC permits
        redistribution with attribution for non-commercial use, and this goes
        back to the copyright holder; LICENSE-DATA.txt carries the attribution.
  3. "ready-to-run, no additional cropping or preprocessing required"
     -> crops are CROP px square (default 512) — a usable training tile, not a
        4096 window someone has to cut up. Nothing to preprocess: open the
        zarr, feed the model.
  4. "representative of only the detectable ink patterns"
     -> positives clear a floor calibrated on known-blank papyrus at a stated
        FPR, and every pair carries the CONDITION-CONTROL AUC (ink vs blank
        sheet of the same preservation) — the direct measurement of the
        issue's stated fear that labels teach a model the surface.

Label codes: 0 unlabelled · 1 ink · 2 certified blank · 3 ink present but
depth ambiguous (flat profile — we refuse to guess a layer).

  python3 tools/make_pairs.py                    # all scrolls with profiles
  SCROLLS=PHerc0139 CROP=512 N=24 python3 tools/make_pairs.py
"""
import glob, json, os, sys, urllib.request, zlib
import concurrent.futures as cf
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_labels_3d import write_zarr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTROOT = os.path.join(ROOT, "out", "pairs")
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH = 128
CROP = int(os.environ.get("CROP", "512"))          # canvas px, ready-to-run
MM_PX = 1000.0 / 9.032                             # pred px per mm
MAXPAIRS = int(os.environ.get("N", "24"))
PROF_DIRS = {"PHerc0139": "lostbook_prof"}
CAL_DIRS = {"PHerc0139": "lostbook", "PHercParis4": "scroll1",
            "PHerc0500P2": "p0500p2", "PHerc0343P": "p0343p"}
ATTRIB = ("Scroll data © Vesuvius Challenge, CC BY-NC 4.0. Redistributed "
          "unmodified under that licence for non-commercial research. "
          "Source: vesuvius-challenge-open-data S3 bucket.")


def get(u, t=180):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=t).read()


_PUB = {}


def pub_for(scroll, meta):
    """Published calls over this window, for the blank keep-out."""
    key = (scroll, meta["seg"], tuple(meta["window"]))
    if key not in _PUB:
        import differential_0139 as _D
        _PUB[key] = _D.pub_crop(meta)
    return _PUB[key]


def depth_label(prof, offsets, dlay, floor, shape_hw):
    """True-3D label from the sliding-window response profile.

    prof: (K, h, w) probabilities, one per 62-layer window start.
    A pixel is ink where its PEAK response clears the floor; the ink is
    written to the layers around that peak window's centre, not smeared
    across the whole band. Flat profiles (no clear peak) get code 3.
    """
    K = prof.shape[0]
    peak = prof.max(0)
    arg = prof.argmax(0)
    ink2d = peak >= floor
    # contrast between best and median response = is the depth meaningful?
    med = np.median(prof, axis=0)
    sharp = (peak - med) >= 0.05
    centres = np.array([o + dlay // 2 for o in offsets])
    return ink2d, sharp, centres[np.clip(arg, 0, K - 1)]


def sheet_depth(img, lo, hi):
    """Per-pixel depth of the SHEET, from the crop's own intensity profile.

    Intensity cannot find ink — density contrast through the ink layer is
    r~0.002, this project's first dead mechanism. But it finds the PAPYRUS
    plainly (sheet is bright, surrounding volume is not), and ink can only lie
    on the sheet. Flattening is imperfect, so the sheet drifts in z across a
    crop; locating it per pixel sharpens depth attribution far past what a
    62-layer reading window can resolve on its own.

    Returns the intensity-weighted centroid of depth within [lo,hi), which is
    steadier than an argmax on noisy 8-bit data.
    """
    band = img[lo:hi].astype(np.float32)
    w = band - band.min(axis=0, keepdims=True)
    tot = w.sum(0)
    z = np.arange(lo, hi, dtype=np.float32)[:, None, None]
    cen = np.where(tot > 1e-3, (w * z).sum(0) / np.maximum(tot, 1e-3),
                   (lo + hi) / 2.0)
    return cen


def build(scroll, calib, profdir):
    floor = json.load(open(os.path.join(calib, "floor.json")))
    ctrl = json.load(open(os.path.join(calib, "condition_control.json")))
    made = 0
    for pf in sorted(glob.glob(os.path.join(profdir, "prof_*.npy"))):
        if made >= MAXPAIRS:
            break
        tag = os.path.basename(pf)[5:-4]
        mf = os.path.join(profdir, f"meta_{tag}.json")
        if not os.path.exists(mf):
            continue
        meta = json.load(open(mf))
        prof = np.load(pf)                                   # (K,1024,1024)
        offs, dlay = meta["offsets"], meta["depth_window"]
        D = meta["stack_depth"]
        ink2d, sharp, depth_of = depth_label(prof, offs, dlay,
                                             floor["floor"], prof.shape[1:])
        if ink2d.sum() < 200:
            continue
        # Two crops per window, because a training set needs both classes:
        # the INK-RICH tile (positives) and a NEGATIVE-RICH tile where the
        # response never approaches the floor at any depth. A crop of pure
        # dense text carries no certified absence, and absence is half the
        # supervision.
        q = CROP // 4                                        # in pred px
        peakmap = prof.max(0)
        # Certified blank = the model is quiet at EVERY depth AND the published
        # detector called nothing within 1.5 mm. The probability cut alone is
        # not certification: our floor only recovers ~14% of known ink, so a
        # low response is weak evidence of absence. The keep-out (which v1 had
        # and v2 dropped) is what makes the negative trustworthy.
        try:
            pubmap = pub_for(scroll, meta)
            called = (pubmap > 128).astype(np.float32)
            kk = min(int(1.5 * MM_PX), called.shape[0] - 1)
            cc = np.pad(called, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
            near = cc[kk:, kk:] - cc[:-kk, kk:] - cc[kk:, :-kk] + cc[:-kk, :-kk]
            far = np.zeros(peakmap.shape, bool)
            far[:near.shape[0], :near.shape[1]] = near <= 0
        except Exception:
            far = np.zeros(peakmap.shape, bool)
        blankmap = (peakmap < (floor["floor"] * 0.35)) & far

        def densest(field):
            cs = np.pad(field.astype(np.float32),
                        ((1, 0), (1, 0))).cumsum(0).cumsum(1)
            bx = cs[q:, q:] - cs[:-q, q:] - cs[q:, :-q] + cs[:-q, :-q]
            return np.unravel_index(int(bx.argmax()), bx.shape)

        picks = [("ink", densest(ink2d))]
        by, bx_ = densest(blankmap)
        if abs(by - picks[0][1][0]) + abs(bx_ - picks[0][1][1]) > q // 2:
            picks.append(("blank", (by, bx_)))

        for kind, (iy, ix) in picks:
            if made >= MAXPAIRS:
                break
            # Snap the PICK ITSELF to a chunk boundary, then derive the origin
            # from it. Snapping the origin instead (and leaving iy/ix at their
            # pre-snap values) cuts the label from different rows than the
            # image is fetched from — a silent offset of up to 124 px, which
            # is ~17% of a letter at this scribe's hand. The window origin is
            # already a multiple of CH, so pred px 4*iy must snap to CH too:
            # iy therefore snaps to a multiple of CH//4 = 32.
            iy = (iy // (CH // 4)) * (CH // 4)
            ix = (ix // (CH // 4)) * (CH // 4)
            y0 = meta["window"][0] + iy * 4
            x0 = meta["window"][1] + ix * 4
            assert y0 % CH == 0 and x0 % CH == 0, "origin must be chunk-aligned"

            # ---- image half: fetch exactly this crop, full depth
            nt = CROP // CH
            cy0, cx0 = y0 // CH, x0 // CH
            img = np.zeros((D, CROP, CROP), np.uint8)
            got = [0]

            def g(cy, cx):
                try:
                    b = get(f"{B}/{SV[scroll][meta['seg']]}0/0/{cy}/{cx}")
                    if len(b) == D * CH * CH:
                        img[:, (cy-cy0)*CH:(cy-cy0+1)*CH,
                            (cx-cx0)*CH:(cx-cx0+1)*CH] = \
                            np.frombuffer(b, np.uint8).reshape(D, CH, CH)
                        got[0] += 1
                except Exception:
                    pass
            with cf.ThreadPoolExecutor(max_workers=16) as ex:
                list(ex.map(lambda p: g(*p),
                            [(cy0+j, cx0+k) for j in range(nt) for k in range(nt)]))
            if got[0] < nt * nt:
                continue

            # ---- label half: TRUE 3D, per-voxel depth
            # Two independent depth signals, intersected:
            #   model  -> WHERE IN Z the ink response peaks (62-layer resolution)
            #   sheet  -> where the papyrus physically is, per pixel, from the
            #             crop's own intensity (sharp, but ink-blind)
            # Ink lies on the sheet, so the model picks the window and the sheet
            # picks the layer inside it. Neither alone is enough.
            lab = np.zeros((D, CROP, CROP), np.uint8)
            sub_ink = ink2d[iy:iy+q, ix:ix+q]
            sub_sharp = sharp[iy:iy+q, ix:ix+q]
            sub_depth = depth_of[iy:iy+q, ix:ix+q]
            half = dlay // 4                                     # model's reach
            tight = max(3, dlay // 12)                           # sheet's reach
            for yy in range(q):
                for xx in range(q):
                    if not sub_ink[yy, xx]:
                        continue
                    code = 1 if sub_sharp[yy, xx] else 3
                    z = int(sub_depth[yy, xx])
                    lo, hi = max(0, z - half), min(D, z + half)
                    if code == 1 and hi - lo > 2 * tight:
                        # refine to the sheet inside the model's window
                        sd = sheet_depth(img[:, yy*4:(yy+1)*4, xx*4:(xx+1)*4],
                                         lo, hi).mean()
                        zc = int(round(float(sd)))
                        lo, hi = max(0, zc - tight), min(D, zc + tight)
                    lab[lo:hi, yy*4:(yy+1)*4, xx*4:(xx+1)*4] = code
            # certified blank: never ink at any depth, comfortably below floor
            blank2d = blankmap[iy:iy+q, ix:ix+q]
            for yy, xx in zip(*np.nonzero(blank2d)):
                lab[:, yy*4:(yy+1)*4, xx*4:(xx+1)*4] = 2

            y0, x0 = int(y0), int(x0)      # numpy ints are not JSON-serialisable
            name = f"{meta['seg'].split('/')[-2][:36]}__{kind}__y{y0}_x{x0}"
            dst = os.path.join(OUTROOT, scroll, name)
            attrs = dict(
                issue="ScrollPrize/villa#192",
                ready_to_run=True, crop_px=int(CROP), pair_kind=kind,
                shape=[int(v) for v in lab.shape],
                label_codes={"0": "unlabelled", "1": "ink (depth resolved)",
                             "2": "certified blank",
                             "3": "ink present, depth ambiguous (flat profile)"},
                depth_method=(
                    "TWO independent signals, intersected. (1) MODEL: the fixed "
                    f"62-layer input window is slid to offsets {offs}; each pixel "
                    "gets a response profile and ink is placed at its PEAK — this "
                    "localises depth only to the window width. (2) SHEET: within "
                    "that window, the crop's own intensity profile gives the "
                    "papyrus surface per pixel (intensity cannot see ink — "
                    "density contrast r~0.002 — but it sees the sheet, and ink "
                    f"lies on it), narrowing the label to +/-{tight} layers. "
                    "Pixels whose model profile is flat are coded 3 (ambiguous) "
                    "rather than assigned a guessed depth."),
                depth_resolution_layers=int(2 * tight),
                scroll=scroll, segment=meta["seg"],
                window_origin_yx=[int(y0), int(x0)],
                floor=float(floor["floor"]),
                floor_blank_fpr=float(floor["blank_fpr"]),
                map_auc_vs_published=float(floor["auc"]),
                condition_control_auc=float(ctrl["auc_near"]),
                condition_control_meaning=("AUC separating known ink from blank "
                                           "sheet INSIDE the text block — same "
                                           "preservation. Directly measures the "
                                           "surface-confound #192 warns about."),
                model="scrollprize/PHerc.1667-iteration-5",
                generator="tools/make_pairs.py", data_licence=ATTRIB)
            write_zarr(os.path.join(dst, "label"), lab, (D, 256, 256), attrs)
            write_zarr(os.path.join(dst, "image"), img, (D, 256, 256),
                       dict(source=meta["seg"], licence=ATTRIB,
                            note="unmodified surface-volume crop, pairs with label/"))
            open(os.path.join(dst, "LICENCE-DATA.txt"), "w").write(ATTRIB + "\n")
            made += 1
            print(f"  {scroll} {name}: ink {100*(lab==1).mean():.2f}% "
                  f"ambiguous {100*(lab==3).mean():.2f}% blank {100*(lab==2).mean():.1f}%")
    return made


SV = {}


def main():
    only = os.environ.get("SCROLLS")
    total = 0
    for scroll, pd in PROF_DIRS.items():
        if only and scroll not in only.split(","):
            continue
        profdir = os.path.join(ROOT, "out", pd)
        calib = os.path.join(ROOT, "out", CAL_DIRS[scroll])
        if not glob.glob(os.path.join(profdir, "prof_*.npy")):
            print(f"{scroll}: no depth profiles yet — run "
                  f"`fleet_lostbook.py profile` first")
            continue
        # per-SEGMENT volume path — each segment has its own, and using
        # one for all of them silently pairs labels with the wrong papyrus.
        SV[scroll] = {t["seg"]: t["sv"] for t in json.load(
            open(os.path.join(ROOT, "findings", "targets.json")))
            if t["scroll"] == scroll}
        total += build(scroll, calib, profdir)
    print(f"\n{total} ready-to-run pairs -> out/pairs/")


if __name__ == "__main__":
    main()
