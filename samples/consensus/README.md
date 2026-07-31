# Sample: cross-energy consensus labels

One segment of PHerc0139, committed so a reviewer can open a working array
without running anything. The other 61 paired segments regenerate with:

```bash
python3 tools/fetch_pub_maps.py PHerc0139     # ds8 published maps, both energies
SCROLL=PHerc0139 python3 tools/crossenergy_1667.py
python3 tools/make_consensus_labels.py
```

Plain zarr v2, zlib, uint8, `dimension_separator: "."`. Codes:

| code | meaning |
| --- | --- |
| 0 | unlabelled — not covered by both scans, or inside the sheet-edge keep-out |
| 1 | **consensus ink** — both independent scans call it |
| 2 | **consensus blank** — neither calls it, clear of the spillover and edge keep-outs |
| 3 | disputed — exactly one scan calls it |

Read it with no dependencies beyond numpy:

```python
import json, zlib, numpy as np
p = "samples/consensus/PHerc0139-20260302000001.zarr"
z = json.load(open(f"{p}/.zarray"))
cert = json.load(open(f"{p}/.zattrs"))        # provenance + agreement stats
gy = -(-z["shape"][0] // z["chunks"][0]); gx = -(-z["shape"][1] // z["chunks"][1])
a = np.zeros(z["shape"], np.uint8)
for i in range(gy):
    for j in range(gx):
        b = np.frombuffer(zlib.decompress(open(f"{p}/{i}.{j}", "rb").read()),
                          np.uint8).reshape(z["chunks"])
        h = min(z["chunks"][0], z["shape"][0] - i*512)
        w = min(z["chunks"][1], z["shape"][1] - j*512)
        a[i*512:i*512+h, j*512:j*512+w] = b[:h, :w]
assert {k: int((a == v).sum()) for k, v in
        (("unlabelled",0),("ink",1),("blank",2),("disputed",3))} == cert["counts_px"]
```

`.zattrs` carries both source volumes and recipes, the measured registration,
agreement against a spatial null, the keep-outs and why, and the limitation:
two energies share the papyrus, so agreement does **not** separate ink from
sheet condition.

Labels only. No scroll image data is redistributed — the bucket path for the
image half is in the certificate. Derived from published ink detections,
CC BY-NC 4.0, © Vesuvius Challenge.
