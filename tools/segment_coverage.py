"""Which auto-grown segments on the unread scrolls actually sit on stored data?

A segment's mesh can be grown into regions the masked volume never wrote. When
that happens the segment looks fine in its metadata — it reports an area in cm2
— but rendering it produces nothing, because the voxels do not exist. PHerc.1447
segment 20250502180708 claims 2.89 cm2 and is 79% empty.

Nobody publishes which segments are solid. This finds out, using HEAD requests
only: for every valid point in a segment's tifxyz, work out which chunk of the
raw volume it lands in, then ask whether that chunk exists.

Output: a table of segments ranked by renderable area, so a GPU gets pointed at
something real.
"""
import urllib.request, concurrent.futures as cf, json, io, sys
import numpy as np
from PIL import Image

B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
CH = 128

# scroll -> its raw volume (the one the segments were grown from)
VOLUMES = {
    "PHerc0800": "20250521135224-8.640um-1.2m-116keV-masked.zarr",
    "PHerc1447": "20250521151220-8.640um-1.2m-116keV-masked.zarr",
    "PHerc1203": "20250820131727-9.362um-1.2m-113keV-masked.zarr",
    "PHerc0332": "20251211183505-2.399um-0.2m-78keV-masked.zarr",
}


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def listdir(prefix):
    """CommonPrefixes under a prefix."""
    out, token = [], None
    for _ in range(20):
        u = f"{B}?list-type=2&prefix={urllib.parse.quote(prefix)}&delimiter=/"
        if token:
            u += "&continuation-token=" + urllib.parse.quote(token)
        try:
            xml = get(u).decode()
        except Exception:
            return out
        for part in xml.split("<Prefix>")[1:]:
            p = part.split("</Prefix>")[0]
            if p != prefix:
                out.append(p)
        if "<IsTruncated>true</IsTruncated>" in xml:
            token = xml.split("<NextContinuationToken>")[1].split("</Next")[0]
        else:
            break
    return out


def find_tifxyz(seg_prefix):
    """Locate a tifxyz directory inside a segment (layout varies)."""
    for sub in listdir(seg_prefix):
        if sub.rstrip("/").endswith("mesh"):
            for inter in listdir(sub):
                for d in listdir(inter):
                    if "tifxyz" in d:
                        return d
                if "tifxyz" in inter:
                    return inter
    return None


def chunk_alive(vol, k):
    try:
        req = urllib.request.Request(f"{B}/{vol}/0/{k[0]}/{k[1]}/{k[2]}", method="HEAD")
        with urllib.request.urlopen(req, timeout=25) as r:
            return k, r.status == 200
    except Exception:
        return k, False


def assess(scroll, seg_prefix):
    vol = f"{scroll}/volumes/{VOLUMES[scroll]}"
    tif = find_tifxyz(seg_prefix)
    if not tif:
        return None
    # `tif` is an S3 KEY prefix, not a URL — it needs the bucket in front.
    try:
        X = np.array(Image.open(io.BytesIO(get(f"{B}/{tif}x.tif")))).astype(np.float64)
        Y = np.array(Image.open(io.BytesIO(get(f"{B}/{tif}y.tif")))).astype(np.float64)
        Z = np.array(Image.open(io.BytesIO(get(f"{B}/{tif}z.tif")))).astype(np.float64)
    except Exception as e:
        print(f"      ! tif read failed for {tif}: {e}", flush=True)
        return None
    try:
        meta = json.loads(get(f"{B}/{tif}meta.json").decode())
    except Exception:
        meta = {}

    v = (X > 0) & (Y > 0) & (Z > 0)
    nvalid = int(v.sum())
    if nvalid == 0:
        return dict(scroll=scroll, seg=seg_prefix.rstrip("/").split("/")[-1],
                    area=meta.get("area_cm2"), valid=0, livefrac=0.0, live_area=0.0,
                    grid=list(X.shape))

    cz = (Z // CH).astype(int); cy = (Y // CH).astype(int); cx = (X // CH).astype(int)
    counts = {}
    for j, i in zip(*np.where(v)):
        counts[(cz[j, i], cy[j, i], cx[j, i])] = counts.get((cz[j, i], cy[j, i], cx[j, i]), 0) + 1
    keys = list(counts)
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        alive = {k for k, ok in ex.map(lambda k: chunk_alive(vol, k), keys) if ok}
    livepts = sum(n for k, n in counts.items() if k in alive)
    frac = livepts / nvalid
    area = meta.get("area_cm2")
    return dict(scroll=scroll, seg=seg_prefix.rstrip("/").split("/")[-1],
                area=area, valid=nvalid, livefrac=frac,
                live_area=(area * frac) if isinstance(area, (int, float)) else None,
                grid=list(X.shape), chunks=len(keys), live_chunks=len(alive))


import urllib.parse
rows = []
for scroll in VOLUMES:
    segs = listdir(f"{scroll}/segments/")
    # PHerc1203 nests its segments one level deeper under "raw/"
    expanded = []
    for s in segs:
        kids = listdir(s)
        if any("tifxyz" in k or k.rstrip("/").endswith("mesh") for k in kids):
            expanded.append(s)
        else:
            expanded.extend(kids or [s])
    print(f"{scroll}: {len(expanded)} segments", flush=True)
    for s in expanded:
        try:
            r = assess(scroll, s)
        except Exception as e:
            print(f"      ! {s} failed: {type(e).__name__}: {e}", flush=True)
            r = None
        if r:
            rows.append(r)
            a = f"{r['area']:.2f}" if isinstance(r["area"], float) else "  ?  "
            la = f"{r['live_area']:.2f}" if isinstance(r.get("live_area"), float) else "  ?  "
            print(f"   {r['seg'][:42]:42s} area {a} cm2  live {100*r['livefrac']:5.1f}%  "
                  f"-> {la} cm2 renderable", flush=True)

rows.sort(key=lambda r: (r.get("live_area") or 0), reverse=True)
json.dump(rows, open("segment_coverage.json", "w"), indent=1)

print("\n" + "="*78)
print("RANKED BY RENDERABLE AREA  (First Letters needs 10 letters in 4 cm2)")
print("="*78)
print(f"{'scroll':11s} {'segment':30s} {'claimed':>8s} {'live%':>7s} {'real':>8s}")
for r in rows[:15]:
    a = f"{r['area']:.2f}" if isinstance(r["area"], float) else "?"
    la = f"{r['live_area']:.2f}" if isinstance(r.get("live_area"), float) else "?"
    print(f"{r['scroll']:11s} {r['seg'][:30]:30s} {a:>8s} {100*r['livefrac']:6.1f}% {la:>8s}")
tot = sum(r.get("live_area") or 0 for r in rows)
print(f"\n{len(rows)} segments assessed; total renderable area {tot:.2f} cm2")
