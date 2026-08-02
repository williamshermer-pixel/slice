#!/usr/bin/env python3
"""One-pod launcher for the whole-pipeline positive control.

Simpler than fleet_lostbook on purpose: the weights come from HuggingFace, so
there is no hub pod and no chunked weight upload. One GPU, one segment, one
answer.

  python3 tools/fleet_control.py launch
  python3 tools/fleet_control.py status
  python3 tools/fleet_control.py harvest
  python3 tools/fleet_control.py terminate     # ALWAYS

ALWAYS TERMINATE. The banked lesson from this project: a pod reading
desiredStatus=EXITED can still be live, and DONE pods bill while sleeping.
`status` here reports `runtime`, which is the field that tells the truth.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fleet_lostbook import api, cget, create_pod, proxy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "control_iter0")
STATE = os.path.join(OUT, "pod.json")
JOB = os.path.join(ROOT, "tools", "pod_control_iter0.py")


def launch():
    os.makedirs(OUT, exist_ok=True)
    src = open(JOB).read()
    import base64
    b64 = base64.b64encode(src.encode()).decode()
    # create_pod already wraps this in ["bash","-c", cmd] — do NOT add another
    # shell layer here or the quoting eats itself.
    #
    # SERVE FIRST, WORK SECOND. The first version of this put the http.server
    # last, so nothing was readable until the job had already finished — six
    # minutes of polling a pod with no way to tell downloading from crashed.
    # Start the server up front and the log is live from the first line.
    # `python` is NOT guaranteed on PATH in these images — only `python3` is.
    # The first two attempts chained with `;`, so a missing `python` failed the
    # server AND the job silently while `sleep infinity` kept the pod looking
    # perfectly healthy. Resolve the interpreter once, up front, and record it.
    cmd = (
        "mkdir -p /workspace/out; "
        "PY=$(command -v python3 || command -v python); "
        "{ echo \"container up $(date -u)\"; echo \"PY=$PY\"; "
        "  echo \"host=$(hostname)\"; } > /workspace/out/log.txt; "
        "cd /workspace/out && ($PY -m http.server 8000 "
        "  >> /workspace/out/serve.log 2>&1 &) ; "
        "$PY -m pip install -q --no-input transformers pillow "
        "  > /workspace/out/pip.log 2>&1; "
        "echo \"pip done rc=$?\" >> /workspace/out/log.txt; "
        f"echo {b64} | base64 -d > /workspace/job.py; "
        "cd /workspace && stdbuf -oL -eL $PY job.py "
        "  >> /workspace/out/log.txt 2>&1; "
        "echo EXIT=$? >> /workspace/out/log.txt; "
        "sleep infinity")
    resp = create_pod("ink-control-iter0", cmd)
    pid = resp["id"] if isinstance(resp, dict) else resp
    json.dump({"pod": pid, "t": time.time()}, open(STATE, "w"))
    print("launched", pid)
    print("poll with: python3 tools/fleet_control.py status")


def _pod():
    return json.load(open(STATE))["pod"]


def status():
    pid = _pod()
    p = api("GET", f"/pods/{pid}")
    rt = p.get("runtime")
    print(f"{pid}  desired={p.get('desiredStatus')}  "
          f"runtime={'LIVE' if rt else 'none'}  ${p.get('costPerHr')}/hr")
    # cget returns (ok, bytes) and shells out to curl — python-urllib's UA is
    # 403'd by the RunPod proxy.
    for name in ("log.txt", "pip.log"):
        ok, data = cget(proxy(pid) + "/" + name, t=30)
        if not ok:
            continue
        tail = data.decode(errors="ignore").strip().split("\n")[-12:]
        print(f"--- {name} tail ---")
        for line in tail:
            print("  ", line[:160])
        return
    print("  (no log yet — pod still provisioning or job not started)")


def harvest():
    pid = _pod()
    os.makedirs(OUT, exist_ok=True)
    got = []
    for f in ("control.json", "ours.png", "theirs.png", "ours.npy",
              "theirs.npy", "log.txt"):
        ok, d = cget(proxy(pid) + "/" + f, t=300)
        if not ok or not d:
            continue
        open(os.path.join(OUT, f), "wb").write(d)
        got.append(f)
    print("harvested:", ", ".join(got) or "nothing")
    p = os.path.join(OUT, "control.json")
    if os.path.exists(p):
        print(json.dumps(json.load(open(p)), indent=1))


def terminate():
    pid = _pod()
    api("DELETE", f"/pods/{pid}")
    print("terminated", pid)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"launch": launch, "status": status, "harvest": harvest,
     "terminate": terminate}[cmd]()
