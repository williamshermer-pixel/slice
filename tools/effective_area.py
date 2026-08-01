#!/usr/bin/env python3
"""How much of the searched sheet could actually HIDE a letter?

This exists because "we searched 245 cm2 and found nothing" is a misleading
sentence, and it was nearly shipped.

The region a conjunction search looks at is what is left after removing called
text, a 1.5 mm spillover keep-out around every call, and a 3-letter keep-out
from every sheet edge (the search's own construction, imported from
conjunction_1667.build_search so the two can never drift again). On a page of text that leftover is not open field — it
is narrow ribbons between the lines. A letter cannot fit in most of it, so most
of that area could not have contained an unnoticed letter no matter how
sensitive the instrument was. Counting it as "searched" inflates the negative.

Reported per segment:

    search_mm2       raw area the search ran over
    hostable_mm2     inscribed radius >= 0.375 letter (a letter mostly fits)
    effective_mm2    inscribed radius >= 0.5 letter (a letter-sized disc fits)
    line_mm2         effective AND room for a 4-letter horizontal run
    max_clearance    largest inscribed circle, in letters

The honest coverage claim for a negative is effective_mm2, and the honest claim
for "no unread WORDS" is line_mm2. Both are typically a small fraction of the
raw area.

    SCROLL=PHerc0139 python3 tools/effective_area.py
"""
import glob, json, os, sys
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS = {"PHerc1667": 1.63, "PHerc0139": 1.61, "PHerc0814": 1.28}
SCROLL = os.environ.get("SCROLL", "PHerc0139")
_DIRS = {"PHerc1667": "s1667"}
OUT = os.path.join(ROOT, "out", _DIRS.get(SCROLL, f"xe_{SCROLL}"))
DS8_UM = 18.064
LETTER_PX = HANDS[SCROLL] * 1000.0 / DS8_UM
KEEPOUT_PX = int(round(1.5 * 1000.0 / DS8_UM))
PX_MM2 = (DS8_UM / 1000.0) ** 2


def main():
    rep, tot = {}, dict(search=0.0, host=0.0, eff=0.0, line=0.0)
    for f in sorted(glob.glob(os.path.join(OUT, "xe_*.npz"))):
        seg = os.path.basename(f)[3:-4]
        d = np.load(f)
        m, ca, cb = d["m"], d["ca"], d["cb"]
        # identical construction to the search that actually runs -- sizing
        # any other region is sizing a fiction
        import conjunction_1667 as _cj
        search = _cj.build_search(m, ca, cb)
        if search.sum() == 0:
            continue
        clear = ndimage.distance_transform_edt(search)
        # clearance is an inscribed RADIUS: a letter-sized disc (diameter one
        # letter) fits where clear >= LETTER_PX/2. The first version demanded
        # clear >= LETTER_PX -- a TWO-letter-wide disc -- then described it as
        # "a letter fits", understating effective area ~4x. Conservative in a
        # safe direction, but wrong words on a number are wrong words.
        host = clear >= 0.375 * LETTER_PX
        eff = clear >= 0.5 * LETTER_PX
        # room for a 4-letter run: a horizontal box 4 letters x 1 letter that
        # stays inside the search region
        run = ndimage.uniform_filter(
            search.astype(np.float32),
            size=(int(LETTER_PX), int(4 * LETTER_PX))) >= 0.99
        line = eff & run

        v = {k: round(float(x.sum()) * PX_MM2, 1) for k, x in
             (("search_mm2", search), ("hostable_mm2", host),
              ("effective_mm2", eff), ("line_mm2", line))}
        v["max_clearance_letters"] = round(float(clear.max()) / LETTER_PX, 2)
        v["effective_pct_of_searched"] = round(
            100 * float(eff.sum()) / float(search.sum()), 2)
        rep[seg] = v
        tot["search"] += v["search_mm2"]; tot["host"] += v["hostable_mm2"]
        tot["eff"] += v["effective_mm2"]; tot["line"] += v["line_mm2"]
        print(f"{seg}  search {v['search_mm2']:8.1f}  hostable "
              f"{v['hostable_mm2']:7.1f}  effective {v['effective_mm2']:7.1f} "
              f"({v['effective_pct_of_searched']:5.2f}%)  4-letter run "
              f"{v['line_mm2']:6.1f}  max clr {v['max_clearance_letters']:.2f}L")

    p = os.path.join(OUT, "effective_area.json")
    json.dump(dict(scroll=SCROLL, letter_mm=HANDS[SCROLL],
                   um_per_px=DS8_UM, totals_mm2=tot, segments=rep),
              open(p, "w"), indent=1)
    print(f"\n{SCROLL} TOTAL  searched {tot['search']/100:7.1f} cm2   "
          f"hostable {tot['host']/100:6.1f} cm2   "
          f"EFFECTIVE {tot['eff']/100:6.1f} cm2 "
          f"({100*tot['eff']/max(tot['search'],1e-9):.1f}% of searched)   "
          f"4-letter-run {tot['line']/100:6.1f} cm2")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
