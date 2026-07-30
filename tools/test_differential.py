"""CALIBRATION HARNESS for the 0139 differential gates.

Rule of this project: never trust a detector you have not calibrated. Before
the gates judge real maps, they must (a) FIRE on synthetic letters planted at
0139's measured hand, (b) stay SILENT on noise, blobs of the wrong size, and
grid-locked artifacts — the three failure modes that produced every retracted
candidate in this campaign.

  python3 tools/test_differential.py
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differential_0139 as D


def blank():
    rng = np.random.default_rng(11)
    return rng.random((1024, 1024)).astype(np.float32) * 0.3


def plant_letters(field, n=5, size=None, advance=None):
    """Letters at his hand (1.09 mm tall), wrapping to new lines at his
    measured 4.57 mm pitch so any count actually fits on the canvas."""
    size = size or int(1.09 * D.MM)          # ~121 px
    advance = advance or int(D.ADVANCE)      # ~77 px
    step = max(advance, size + 6)
    per_row = max(1, (1024 - 260) // step)
    for i in range(n):
        y = 200 + (i // per_row) * int(D.PITCH)
        x = 150 + (i % per_row) * step
        if y + size > 1024 or x + size > 1024:
            continue
        f = field[y:y + size, x:x + size]
        if f.shape != (size, size):
            continue
        f[:, :max(3, size // 8)] = 1.0                    # left stem
        f[max(0, size // 2 - 2):size // 2 + 2, :] = 1.0   # crossbar
        f[:, -max(3, size // 8):] = 1.0                   # right stem
    return field


def plant_grid(field, pitch=64, size=None):
    """The artifact signature: grid-locked squares at the model's block pitch."""
    size = size or int(1.09 * D.MM)
    for gy in range(300, 700, pitch * 2):
        for gx in range(300, 700, pitch * 2):
            field[gy:gy + size, gx:gx + size] = 1.0
    return field


def plant_solid(field, n=5, size=None):
    """Solid letter-SIZED patches: right size, wrong shape. The condition
    artifact that cleared size+rhythm gates all through this campaign."""
    size = size or int(1.09 * D.MM)
    step = size + 6
    for i in range(n):
        y, x = 200 + (i // 6) * int(D.PITCH), 150 + (i % 6) * step
        if y + size <= 1024 and x + size <= 1024:
            field[y:y + size, x:x + size] = 1.0
    return field


def run(name, ours, pub=None, expect=None):
    pub = np.zeros((1024, 1024), np.float32) if pub is None else pub
    mask, comps, r, n_sized = D.gate(ours, pub)   # the production gate itself
    passes = 2 <= len(comps) <= 9
    ok = "" if expect is None else ("  OK" if passes == expect else "  ** WRONG **")
    print(f"{name:34} sized {n_sized:3d} -> stroke {len(comps):3d}  "
          f"rhythm {r:.3f}  passes {str(passes):5}{ok}")
    return passes == expect if expect is not None else True


def main():
    print(f"scale: {D.MM:.1f} px/mm | letter gate {D.LETTER_LO}-{D.LETTER_HI} px "
          f"({D.LETTER_LO/D.MM:.2f}-{D.LETTER_HI/D.MM:.2f} mm) | "
          f"advance {D.ADVANCE:.0f} px")
    results = []

    # POSITIVE: letters at his hand, published map empty -> must fire
    results.append(run("letters @ his hand (1.09mm)",
                       plant_letters(blank()), expect=True))

    # NULL 1: pure noise -> must stay silent
    results.append(run("pure noise (null)", blank(), expect=False))

    # NULL 2: letters ALREADY CALLED by published map -> not new ink.
    # pub band covers the planted line (y 200+, x 150+) so nothing is "new".
    f = plant_letters(blank())
    pub = np.zeros((1024, 1024), np.float32)
    pub[150:400, 100:1024] = 255.0
    results.append(run("letters already published", f, pub, expect=False))

    # NULL 3: wrong-scale blobs (Scroll 1's 3mm hand on his scroll)
    results.append(run("blobs @ wrong hand (3.0mm)",
                       plant_letters(blank(), n=4, size=int(3.0 * D.MM)),
                       expect=False))

    # NULL 4: grid-locked artifacts at the model's block pitch
    results.append(run("grid artifacts (64px pitch)",
                       plant_grid(blank()), expect=False))

    # SATURATION: too many comps = condition patch, not a line of text
    results.append(run("30 comps (saturation)",
                       plant_letters(blank(), n=30), expect=False))

    # NULL 5 — THE SHAPE TEST: solid patches at the RIGHT size and rhythm.
    # These passed every gate this campaign had until now.
    results.append(run("solid patches (right size)",
                       plant_solid(blank()), expect=False))

    # defog + render must not throw
    d = D.defog(plant_letters(blank()))
    assert d.shape == (1024, 1024) and d.dtype == np.uint8, "defog broken"
    print(f"{'defog':34} ok (range {d.min()}-{d.max()})")

    bad = results.count(False)
    print(f"\n{len(results)-bad}/{len(results)} gate checks correct")
    if bad:
        sys.exit("CALIBRATION FAILED — do not trust these gates")
    print("gates calibrated: fire on his-hand letters, silent on all four nulls")


if __name__ == "__main__":
    main()
