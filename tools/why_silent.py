#!/usr/bin/env python3
"""WHY IS THIS SHEET SILENT? — a per-sheet diagnostic for unrecovered ink.

THE PROBLEM THIS SOLVES, IN THEIR WORDS. Vesuvius Challenge's own open-problems
doc (July 2026) lists six reasons ink may fail to appear -- weak scan signal,
misplaced surface, mislocated labels, wrong architecture, differing ink
chemistry, or signal present but unusable -- and then says:

    "we do not always know which part of the pipeline is limiting us and the
     limiting factor is to be assessed on a scroll-by-scroll basis"
    "This is why better diagnostics matter just as much as better models --
     without them, it's hard to know which of these failure modes you're even
     fighting."

Nobody has published such a diagnostic. This is one. It answers, per sheet,
WHICH gate a silence fails at -- and it needs no GPU, no model and no labels,
only HEAD requests and the published maps.

THE GATES, in the order a signal has to survive them
----------------------------------------------------
  1 PHYSICS      Can this scan resolve ink at all? Ink is a ~15 um layer, and
                 morphological signal is measured to hold to ~2.04 um/px and
                 collapse by >=3.4 um (Angelotti et al., Sci Rep, Mar 2026).
                 A 7.91 um scan is past the cliff; nothing downstream can fix it.

  2 PROTOCOL     Was it scanned on the recipe that works? Measured across all
                 420 published maps: 0.22 m / 78 keV yields ~30% more confident
                 ink than 59 keV ON THE SAME SEGMENTS, and off-recipe scans
                 (0.4 m / 111 keV) carry roughly half. Protocol predicts yield.

  3 DATA         Does the surface volume actually exist? Measured 2026-08-02:
                 every Scroll 1 `-L1` volume checked is only 30-37% populated,
                 while its 2.4 um sibling is 71-85%. A sheet can read as silent
                 simply because two thirds of its tiles were never written.
                 THIS GATE IS THE ONE EVERYONE SKIPS and it is free to check.

  4 DETECTION    Did the model commit? Absolute score, not a relative cutoff.
                 A top-decile threshold calls 10% of ANY sheet including a
                 blank one, so silence is invisible to it; p99 against a fixed
                 bar is not.

A sheet that clears 1-3 and fails 4 is the interesting case: good scan, good
protocol, real data, and still no ink. That is "no ink recovered yet" rather
than "no ink", and it is the only category worth pointing a model at.

NOTHING HERE DETECTS INK. It reads Vesuvius Challenge's published maps and
their volume metadata and says which failure mode a silence belongs to.
Scroll data CC BY-NC 4.0, (c) Vesuvius Challenge.

    python3 tools/why_silent.py --scroll PHercParis4
    python3 tools/why_silent.py --all --out out/why_silent.json
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com"
UA = {"User-Agent": "Mozilla/5.0"}

CLIFF_UM = 3.4          # morphological ink signal collapses beyond this
GOOD_UM = 2.04          # holds cleanly below this
OPT_PROP, OPT_KEV = 0.22, 78
CONFIDENT = 200         # absolute score bar, same on every sheet
SILENT_P99 = 200
COVERAGE_OK = 70.0      # percent of level-5 tiles that must exist


def head_ok(url, timeout=40):
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, headers=UA, method="HEAD"), timeout=timeout)
        return True
    except Exception:
        return False


def get(url, timeout=90):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def coverage(vol_url, level=5, workers=24):
    """Percent of tiles actually written at a coarse level. Cheap: HEAD only."""
    try:
        za = json.loads(get(f"{vol_url}/{level}/.zarray").decode())
    except Exception:
        return None
    _, h, w = za["shape"]
    _, cy, cx = za["chunks"]
    gy, gx = -(-h // cy), -(-w // cx)
    jobs = [(i, j) for i in range(gy) for j in range(gx)]
    with cf.ThreadPoolExecutor(workers) as ex:
        got = sum(ex.map(lambda j: head_ok(f"{vol_url}/{level}/0/{j[0]}/{j[1]}"), jobs))
    return round(100.0 * got / max(len(jobs), 1), 1)


def protocol(volume_name):
    m = re.match(r"([\d.]+)um-([\d.]+)m-(\d+)keV", volume_name)
    if m:
        return float(m.group(1)), float(m.group(2)), int(m.group(3))
    m = re.match(r"([\d.]+)um-(\d+)keV", volume_name)
    if m:
        return float(m.group(1)), None, int(m.group(2))
    return None, None, None


def verdict(scan_um, prop, kev, cov, p99, conf_pct):
    """Which gate does this silence fail at?"""
    if scan_um and scan_um >= CLIFF_UM:
        return ("PHYSICS", f"{scan_um} um is past the ~{CLIFF_UM} um cliff where "
                           "morphological ink signal collapses; no downstream fix")
    if cov is not None and cov < COVERAGE_OK:
        return ("DATA", f"only {cov}% of surface-volume tiles exist — the sheet is "
                        "largely unwritten, so silence says nothing about ink")
    off = []
    if prop is not None and abs(prop - OPT_PROP) > 0.03:
        off.append(f"{prop} m propagation (recipe is {OPT_PROP})")
    if kev is not None and abs(kev - OPT_KEV) > 6:
        off.append(f"{kev} keV (recipe is {OPT_KEV})")
    if p99 is not None and p99 >= SILENT_P99:
        return ("INK FOUND", f"p99 {p99}, {conf_pct:.2f}% confident calls")
    if off:
        return ("PROTOCOL", "scanned off-recipe: " + "; ".join(off) +
                            " — measured to roughly halve recovered ink")
    return ("UNRECOVERED",
            f"good scan ({scan_um} um, {prop} m, {kev} keV), {cov}% data present, "
            f"and the model still did not commit (p99 {p99}). "
            "This is 'no ink recovered yet', not 'no ink'.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scroll")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "why_silent.json"))
    ap.add_argument("--check-coverage", action="store_true", default=True)
    args = ap.parse_args()

    cat = json.load(open(os.path.join(ROOT, "public", "ink-maps.json")))
    sil = {}
    p = os.path.join(ROOT, "out", "silence", "silence.json")
    if os.path.exists(p):
        for r in json.load(open(p))["maps_detail"]:
            sil[(r["scroll"], r["segment"], r["model"])] = r

    ents = [e for e in cat["entries"]
            if args.all or not args.scroll or e["scroll"] == args.scroll]
    print(f"{len(ents)} sheets\n")
    rows = []
    hdr = (f"{'scroll':12s} {'segment':16s} {'um':>6} {'keV':>4} "
           f"{'p99':>4} {'cov%':>6}  verdict")
    print(hdr)
    print("-" * len(hdr))
    for e in ents:
        um, prop, kev = protocol(e["volume"])
        m0 = e["maps"][0]
        r = sil.get((e["scroll"], e["segment"][:14], m0["model"]))
        p99 = r["p99"] if r else None
        confp = 100 * r["conf_frac"] if r else 0.0
        # Coverage is the expensive-ish part; only pay it where it can change
        # the answer — a sheet with ink already told us its data is there.
        cov = None
        if args.check_coverage and (p99 is None or p99 < SILENT_P99):
            cov = coverage(e["url"])
        v, why = verdict(um, prop, kev, cov, p99, confp)
        rows.append(dict(scroll=e["scroll"], segment=e["segment"][:14],
                         volume=e["volume"], voxel_um=um, propagation_m=prop,
                         energy_kev=kev, coverage_pct=cov, p99=p99,
                         confident_pct=round(confp, 2), verdict=v, why=why,
                         surface_id=e["id"]))
        if v != "INK FOUND":
            print(f"{e['scroll']:12s} {e['segment'][:14]:16s} {str(um):>6} "
                  f"{str(kev):>4} {str(p99):>4} {str(cov):>6}  {v}")

    from collections import Counter
    c = Counter(r["verdict"] for r in rows)
    print("\n=== verdicts ===")
    for k, n in c.most_common():
        print(f"  {k:12s} {n:4d}")
    hunt = [r for r in rows if r["verdict"] == "UNRECOVERED"]
    print(f"\nUNRECOVERED — good scan, real data, no ink: {len(hunt)}")
    for r in hunt:
        print(f"  {r['scroll']} {r['segment']} {r['voxel_um']}um "
              f"cov {r['coverage_pct']}% p99 {r['p99']}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(dict(
        note="Per-sheet diagnosis of WHY a published ink map is silent. Gates: "
             "physics (resolution cliff), protocol (scan recipe), data (does "
             "the surface volume exist), detection (absolute score). Reads "
             "Vesuvius Challenge's published maps; detects no ink itself.",
        gates=dict(cliff_um=CLIFF_UM, optimal=[OPT_PROP, OPT_KEV],
                   confident_bar=CONFIDENT, coverage_ok_pct=COVERAGE_OK),
        counts=dict(c), sheets=rows), open(args.out, "w"), indent=1)
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
