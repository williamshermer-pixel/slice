"""Load combed sheet tracks into Blender and rig a flythrough.

Run inside Blender: Scripting tab > Open > this file > Run Script.
Point TRACKS_CSV at the CSV that comb3d.py wrote.

Units are millimetres, so a scroll winding is a few mm across and the default
camera clipping works without fighting it.

What you get:
  - every track as its own curve object, under a "Sheets" collection
  - a thin bevel so they render as tubes rather than invisible hairlines
  - colour by track length (long confident runs read hot, short ones cool)
  - a camera constrained to follow the longest track — scrub the timeline and
    you are driving along the sheet
"""
import bpy, csv, math
from collections import defaultdict

TRACKS_CSV = "/private/tmp/tracks.csv"   # <- edit me
BEVEL_MM = 0.004                          # tube radius; ~4 um, thin as a fibre
MAX_TRACKS = 4000                         # raise if your machine is happy
FLY_FRAMES = 600


def clear():
    for c in ("Sheets",):
        col = bpy.data.collections.get(c)
        if col:
            for o in list(col.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(col)


def load(path):
    tracks = defaultdict(list)
    with open(path) as f:
        for row in csv.DictReader(f):
            tracks[int(row["track"])].append(
                (float(row["x_mm"]), float(row["y_mm"]), float(row["z_mm"])))
    return tracks


def ramp(t):
    """cool -> hot by normalised track length."""
    return (0.15 + 0.85 * t, 0.35 + 0.35 * t, 0.9 - 0.7 * t, 1.0)


def main():
    clear()
    col = bpy.data.collections.new("Sheets")
    bpy.context.scene.collection.children.link(col)

    tracks = load(TRACKS_CSV)
    items = sorted(tracks.items(), key=lambda kv: -len(kv[1]))[:MAX_TRACKS]
    if not items:
        print("no tracks found — check TRACKS_CSV")
        return
    longest = max(len(v) for _, v in items)

    mats = []
    for i in range(8):
        m = bpy.data.materials.new(f"sheet_{i}")
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = ramp(i / 7)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.55
        mats.append(m)

    for tid, pts in items:
        cu = bpy.data.curves.new(f"track_{tid}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = BEVEL_MM
        cu.bevel_resolution = 1
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, (x, y, z) in enumerate(pts):
            sp.points[i].co = (x, y, z, 1.0)
        ob = bpy.data.objects.new(f"track_{tid}", cu)
        ob.data.materials.append(mats[min(7, int(7 * len(pts) / longest))])
        col.objects.link(ob)

    # camera that drives along the longest track
    best_id, best_pts = items[0]
    path_cu = bpy.data.curves.new("flightpath", "CURVE")
    path_cu.dimensions = "3D"
    sp = path_cu.splines.new("POLY")
    sp.points.add(len(best_pts) - 1)
    for i, (x, y, z) in enumerate(best_pts):
        sp.points[i].co = (x, y, z, 1.0)
    path = bpy.data.objects.new("flightpath", path_cu)
    col.objects.link(path)
    path_cu.use_path = True
    path_cu.path_duration = FLY_FRAMES

    cam_data = bpy.data.cameras.new("SheetCam")
    cam_data.clip_start = 0.001
    cam_data.clip_end = 100.0
    cam_data.lens = 24
    cam = bpy.data.objects.new("SheetCam", cam_data)
    col.objects.link(cam)
    con = cam.constraints.new("FOLLOW_PATH")
    con.target = path
    con.use_curve_follow = True
    bpy.context.scene.camera = cam
    bpy.context.scene.frame_end = FLY_FRAMES

    print(f"loaded {len(items)} tracks, longest {longest} points")
    print("camera 'SheetCam' follows the longest track — scrub the timeline to drive")


main()
