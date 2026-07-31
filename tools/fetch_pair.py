"""FETCH the image half of a label pair — makes a #192 deliverable
"ready-to-run" without redistributing CC BY-NC scroll data.

Reads a label directory produced by make_labels_3d.py, pulls the exact
surface-volume window from the public bucket, and writes `image/` as zarr
beside `label/` with identical shape and grid. After this, image/label are a
drop-in training pair.

  python3 tools/fetch_pair.py out/labels3d/PHercParis4/<window-dir> [...]
"""
import json, os, sys, urllib.request, zlib
import concurrent.futures as cf
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_labels_3d import write_zarr

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH = 128


def get(u, t=120):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=t).read()


def fetch(dstdir):
    attrs = json.load(open(os.path.join(dstdir, "label", ".zattrs")))
    sv = attrs["surface_volume"]
    y0, x0 = attrs["window_origin_yx"]
    R = attrs["window_size"]
    zlo, zhi = attrs["depth_band"]
    za = json.loads(get(f"{B}/{sv}0/.zarray").decode())
    D = za["shape"][0]
    cy0, cx0, nt = y0 // CH, x0 // CH, R // CH
    stack = np.zeros((zhi, R, R), np.uint8)
    got = [0]

    def g(cy, cx):
        try:
            b = get(f"{B}/{sv}0/0/{cy}/{cx}")
            if len(b) == D * CH * CH:
                stack[:, (cy-cy0)*CH:(cy-cy0+1)*CH, (cx-cx0)*CH:(cx-cx0+1)*CH] = \
                    np.frombuffer(b, np.uint8).reshape(D, CH, CH)[:zhi]
                got[0] += 1
        except Exception:
            pass
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(lambda q: g(*q),
                    [(cy0+j, cx0+k) for j in range(nt) for k in range(nt)]))
    write_zarr(os.path.join(dstdir, "image"), stack, (zhi, 512, 512),
               dict(source=sv, window_origin_yx=[y0, x0],
                    layers=f"0..{zhi} of the {D}-layer stack",
                    note="fetched from the public bucket by tools/fetch_pair.py"))
    print(f"{os.path.basename(dstdir)}: image {stack.shape} "
          f"({got[0]}/{nt*nt} chunks)")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        fetch(d)
