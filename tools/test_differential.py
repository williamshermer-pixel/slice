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


def blank(n=1024):
    rng = np.random.default_rng(11)
    return rng.random((n, n)).astype(np.float32) * 0.3


def plant_letters(field, n=5, size=None, advance=None):
    """Letters at his hand (1.09 mm tall), wrapping to new lines at his
    measured 4.57 mm pitch so any count actually fits on the canvas."""
    size = size or int(D.LETTER_MM * D.MM)
    advance = advance or int(D.ADVANCE)      # ~77 px
    step = max(advance, size + 6)
    N = field.shape[0]
    per_row = max(1, (N - 260) // step)
    for i in range(n):
        y = 200 + (i // per_row) * int(D.PITCH)
        x = 150 + (i % per_row) * step
        if y + size > N or x + size > N:
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
    size = size or int(D.LETTER_MM * D.MM)
    for gy in range(300, 700, pitch * 2):
        for gx in range(300, 700, pitch * 2):
            field[gy:gy + size, gx:gx + size] = 1.0
    return field


def plant_solid(field, n=5, size=None):
    """Solid letter-SIZED patches: right size, wrong shape. The condition
    artifact that cleared size+rhythm gates all through this campaign."""
    size = size or int(D.LETTER_MM * D.MM)
    step = size + 6
    N = field.shape[0]
    per_row = max(1, (N - 260) // step)
    for i in range(n):
        y = 200 + (i // per_row) * int(D.PITCH)
        x = 150 + (i % per_row) * step
        if y + size <= N and x + size <= N:
            field[y:y + size, x:x + size] = 1.0
    return field


def run(name, ours, pub=None, expect=None):
    pub = np.zeros(ours.shape, np.float32) if pub is None else pub
    # synthetic field: letters at 1.0, noise <=0.3, so 0.5 is the
    # equivalent of a calibrated floor. Real runs must calibrate.
    mask, comps, r, n_sized = D.gate(ours, pub, floor=0.5)
    passes = 2 <= len(comps) <= 9
    ok = "" if expect is None else ("  OK" if passes == expect else "  ** WRONG **")
    print(f"{name:34} sized {n_sized:3d} -> stroke {len(comps):3d}  "
          f"rhythm {r:.3f}  passes {str(passes):5}{ok}")
    return passes == expect if expect is not None else True


def main():
    print(f"scroll {D.SCROLL} | mode {D.MODE} | scale {D.MM:.1f} px/mm | "
          f"letter gate {D.LETTER_LO}-{D.LETTER_HI} px "
          f"({D.LETTER_LO/D.MM:.2f}-{D.LETTER_HI/D.MM:.2f} mm) | "
          f"advance {D.ADVANCE:.0f} px")
    shape = D.MODE == "shape"
    if not shape:
        print("envelope mode: the SHAPE gate is deliberately off (it recovers\n"
              "only ~10% of this scribe's known letters), so solid letter-sized\n"
              "mass is EXPECTED to reach the spatial null rather than die here.")
    print()
    results = []
    big = int(D.LETTER_MM * D.MM) * 7 + 400      # fits >=12 letters at any hand

    # POSITIVE: letters at the configured hand, published map empty -> fire
    results.append(run(f"letters @ hand ({D.LETTER_MM}mm)",
                       plant_letters(blank()), expect=True))

    # NULL 1: pure noise
    results.append(run("pure noise (null)", blank(), expect=False))

    # NULL 2: letters ALREADY CALLED by the published map -> not new ink
    f = plant_letters(blank())
    pub = np.zeros((1024, 1024), np.float32)
    pub[150:, 100:] = 255.0
    results.append(run("letters already published", f, pub, expect=False))

    # NULL 3: another scribe's ruler. 5x the configured letter is outside even
    # envelope mode's 3x merged-run allowance, so it must die on size alone.
    wrong = D.LETTER_MM * 5.0
    results.append(run(f"blobs @ wrong hand ({wrong:.1f}mm)",
                       plant_letters(blank(big), n=4, size=int(wrong * D.MM)),
                       expect=False))

    # NULL 4: grid-locked artifacts at the model's output block pitch
    results.append(run("grid artifacts (64px pitch)",
                       plant_grid(blank()), expect=False))

    # SATURATION: more comps than a line of text -> condition patch
    results.append(run("15 comps (saturation)",
                       plant_letters(blank(big), n=15), expect=False))

    # NULL 5 - THE SHAPE TEST: solid patches at the RIGHT size and rhythm.
    # In shape mode these must die here. In envelope mode they are expected
    # to survive to the spatial null, which is what actually kills them.
    results.append(run("solid patches (right size)",
                       plant_solid(blank(big)), expect=shape is False))

    # defog + render must not throw
    d = D.defog(plant_letters(blank()))
    assert d.shape == (1024, 1024) and d.dtype == np.uint8, "defog broken"
    print(f"{'defog':34} ok (range {d.min()}-{d.max()})")

    bad = results.count(False)
    print(f"\n{len(results)-bad}/{len(results)} gate checks correct")
    if bad:
        sys.exit("CALIBRATION FAILED — do not trust these gates")
    print(f"gates calibrated for {D.SCROLL} at {D.LETTER_MM} mm ({D.MODE} mode)")


if __name__ == "__main__":
    main()
