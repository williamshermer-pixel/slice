"""View combed tracks over the actual volume in napari.

Blender is the better viewport for flying a camera; napari is the better bench,
because it puts the tracks on top of the real voxels instead of on their own.
Being able to see a walker sitting on the ridge it claims to be following is
what tells you whether it is riding one sheet or hopping between two.

    pip install "napari[all]" zarr
    python napari_view.py
"""
import csv
from collections import defaultdict

import numpy as np
import napari
import zarr

VOL = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/"
       "PHerc0800/volumes/20250521135224-8.640um-1.2m-116keV-masked.zarr")
TRACKS_CSV = "tracks.csv"
UM = 8.64
ZC, CY, CX, N = 92, 45, 28, 5      # must match comb3d.py


def main():
    # zarr streams straight off the bucket; only the region we look at is read
    z = zarr.open(VOL, mode="r")
    lvl = z["0"]
    z0, z1 = ZC * 128, (ZC + 1) * 128
    y0, y1 = CY * 128, (CY + N) * 128
    x0, x1 = CX * 128, (CX + N) * 128
    print(f"reading {z1-z0} x {y1-y0} x {x1-x0} voxels …")
    block = np.asarray(lvl[z0:z1, y0:y1, x0:x1])

    tracks = defaultdict(list)
    with open(TRACKS_CSV) as f:
        for row in csv.DictReader(f):
            tracks[int(row["track"])].append((
                float(row["z_mm"]) * 1000 / UM - z0,
                float(row["y_mm"]) * 1000 / UM - y0,
                float(row["x_mm"]) * 1000 / UM - x0,
            ))

    # napari Tracks layer wants [track_id, t, z, y, x]; using z as time lets you
    # scrub through the stack and watch the swarm advance slice by slice
    data = []
    for tid, pts in tracks.items():
        for (pz, py, px) in pts:
            data.append([tid, pz, pz, py, px])
    data = np.array(data, dtype=float)
    print(f"{len(tracks)} tracks, {len(data)} points")

    v = napari.Viewer(ndisplay=3)
    v.add_image(block, name="PHerc0800", colormap="gray",
                contrast_limits=[np.percentile(block[block > 0], 1),
                                 np.percentile(block[block > 0], 99)],
                rendering="attenuated_mip")
    v.add_tracks(data, name="swarm", tail_length=200, colormap="turbo")
    napari.run()


if __name__ == "__main__":
    main()
