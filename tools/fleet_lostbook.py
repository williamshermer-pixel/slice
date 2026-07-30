"""FLEET LOSTBOOK launcher — tuned-eyes differential mapping of PHerc0139.

Creates a hub pod (receives the 320 MB honest weights by chunked PUT through
its :8000 proxy) plus worker pods that pull the weight parts from the hub.
All pods run tools/pod_lostbook.py over their segment shard.

  python3 tools/fleet_lostbook.py launch [n_pods]
  python3 tools/fleet_lostbook.py upload          # push weights to hub
  python3 tools/fleet_lostbook.py status
  python3 tools/fleet_lostbook.py harvest         # pull maps to out/lostbook/
  python3 tools/fleet_lostbook.py terminate       # ALWAYS run when done

State in out/lostbook/fleet.json. ALWAYS terminate pods.
"""
import base64, hashlib, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# SCROLL/OUTDIR env let one launcher fly any scroll. Default = the lost book.
SCROLL = os.environ.get("SCROLL", "PHerc0139")
OUT = os.path.join(ROOT, "out", os.environ.get("OUTDIR", "lostbook"))
os.makedirs(OUT, exist_ok=True)
STATE = os.path.join(OUT, "fleet.json")
# "none" => base iter-5, correct for any scroll we have not fine-tuned on.
WEIGHTS = os.environ.get("WEIGHTS", "tuned")
# Coverage targets. Low aims land OFF-SHEET on large segments (Scroll 1
# margins fetch sparse), and the differential does not need empty
# windows: a 30%-covered text window is 70% uncalled sheet, which IS
# the hunting ground. Raise the aims on big-segment scrolls.
AIMS = os.environ.get("AIMS", "0.30,0.12,0.04")
WPT = os.path.join(ROOT, "out", "bootstrap", "tuned_0139_honest.pt")
PART = 8 * 1024 * 1024   # proxy kills PUT bodies much larger than this
API = "https://rest.runpod.io/v1"
GPUS = ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000"]
IMAGE = "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"


def key():
    for line in open(os.path.expanduser("~/.comfyui-mcp/.env")):
        if line.startswith("RUNPOD_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("no RUNPOD_API_KEY")


def api(method, path, body=None):
    r = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key()}",
                 "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=60).read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:400]}")


def segs():
    t = json.load(open(os.path.join(ROOT, "findings", "targets.json")))
    ss = [s for s in t if s["scroll"] == SCROLL]
    only = os.environ.get("ONLY")   # comma-separated seg substrings
    if only:
        keys = [k for k in only.split(",") if k]
        ss = [s for s in ss if any(k in s["seg"] for k in keys)]
    return ss


def job_script(shard, wsrc, tag):
    src = open(os.path.join(ROOT, "tools", "pod_lostbook.py")).read()
    src = src.replace("__SEGS__", json.dumps(shard))
    src = src.replace("__WSRC__", wsrc).replace("__TAG__", tag)
    src = src.replace("__AIMS__",
                      json.dumps([float(a) for a in AIMS.split(",")]))
    b64 = base64.b64encode(src.encode()).decode()
    return (f"cd /workspace && pip install -q transformers==4.57.6 pillow "
            f"hf_transfer && "
            f"echo '{b64}' | base64 -d > /workspace/job.py && "
            f"python /workspace/job.py")


def create_pod(name, cmd):
    last = None
    for gpu in GPUS:
        body = {"name": name, "imageName": IMAGE, "gpuTypeIds": [gpu],
                "gpuCount": 1, "cloudType": "SECURE", "containerDiskInGb": 40,
                "volumeInGb": 0, "ports": ["8000/http"],
                "dockerStartCmd": ["bash", "-c", cmd]}
        try:
            return api("POST", "/pods", body)
        except RuntimeError as e:
            last = e
    raise last


def proxy(pid):
    return f"https://{pid}-8000.proxy.runpod.net"


def launch(n):
    ss = segs()
    shards = [ss[i::n] for i in range(n)]
    # hub first: its id feeds the workers' WSRC
    hub_cmd = job_script(shards[0],
                         "none" if WEIGHTS == "none" else "local", "s0")
    hub = create_pod(f"{SCROLL.lower()}-hub", hub_cmd)
    pods = [{"id": hub["id"], "name": "lostbook-hub", "tag": "s0",
             "n_segs": len(shards[0])}]
    print(f"hub {hub['id']} ({len(shards[0])} segs)")
    for i in range(1, n):
        cmd = job_script(shards[i],
                         "none" if WEIGHTS == "none" else proxy(hub["id"]),
                         f"s{i}")
        p = create_pod(f"{SCROLL.lower()}-w{i}", cmd)
        pods.append({"id": p["id"], "name": f"lostbook-w{i}", "tag": f"s{i}",
                     "n_segs": len(shards[i])})
        print(f"w{i} {p['id']} ({len(shards[i])} segs)")
    json.dump({"pods": pods, "scroll": SCROLL, "weights": WEIGHTS,
               "launched": time.strftime("%F %T")},
              open(STATE, "w"), indent=1)
    print(f"state -> {STATE}")
    print("next: " + ("status (no weight upload needed)" if WEIGHTS == "none"
                      else "python3 tools/fleet_lostbook.py upload"))


def put(url, path):
    """curl PUT — the proxy WAF 403s python-urllib's user agent."""
    import subprocess
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                        "-m", "120", "-A", "Mozilla/5.0", "-X", "PUT",
                        "--data-binary", f"@{path}", url],
                       capture_output=True, text=True)
    return r.stdout.strip() == "200"


def upload():
    import tempfile
    st = json.load(open(STATE))
    hub = proxy(st["pods"][0]["id"])
    data = open(WPT, "rb").read()
    md5 = hashlib.md5(data).hexdigest()
    parts = [data[i:i + PART] for i in range(0, len(data), PART)]
    print(f"{len(data)} bytes, {len(parts)} parts, md5 {md5}")
    tmp = tempfile.mkdtemp()
    for j, p in enumerate(parts):
        pf = os.path.join(tmp, "part")
        open(pf, "wb").write(p)
        for a in range(20):
            if put(f"{hub}/tuned.part{j}", pf):
                print(f"part{j} up ({len(p)} bytes)", flush=True)
                break
            print(f"part{j} attempt {a} failed", flush=True)
            time.sleep(8)
        else:
            sys.exit(f"part{j} failed")
    mf = os.path.join(tmp, "manifest")
    open(mf, "w").write(json.dumps(
        {"parts": len(parts), "sizes": [len(p) for p in parts], "md5": md5}))
    for a in range(20):
        if put(f"{hub}/tuned.manifest", mf):
            print("manifest up — fleet is armed")
            return
        time.sleep(8)
    sys.exit("manifest failed")


def cget(url, dst=None, t=180):
    """curl GET — WAF-safe (python-urllib's UA is 403'd by the proxy)."""
    import subprocess
    a = ["curl", "-s", "-f", "-m", str(t), "-A", "Mozilla/5.0", url]
    if dst:
        a += ["-o", dst]
    r = subprocess.run(a, capture_output=True)
    return (r.returncode == 0, r.stdout)


def status():
    st = json.load(open(STATE))
    for p in st["pods"]:
        try:
            ok, body = cget(f"{proxy(p['id'])}/out/progress.txt", t=20)
            pr = body.decode().strip().splitlines() if ok else []
            done = "DONE" in (pr[-1] if pr else "")
            print(f"{p['name']}: {len(pr)} lines | {pr[-1] if pr else '(empty)'}"
                  + (" [DONE]" if done else ""))
        except Exception as e:
            print(f"{p['name']}: unreachable ({e})")


def harvest():
    st = json.load(open(STATE))
    got = 0
    for p in st["pods"]:
        base = proxy(p["id"])
        try:
            names = []
            for wi in range(3):
                for si in range(p["n_segs"]):
                    for pre in ("map", "tex", "meta"):
                        ext = "json" if pre == "meta" else "npy"
                        names.append(f"{pre}_{p['tag']}_{si}_{wi}.{ext}")
            names += ["progress.txt", "done.json", "error.txt"]
            for nm in names:
                perpod = nm in ("progress.txt", "done.json", "error.txt")
                dst = os.path.join(OUT, f"{p['tag']}_{nm}" if perpod else nm)
                if os.path.exists(dst) and nm.endswith(".npy"):
                    continue                      # already harvested
                if cget(f"{base}/out/{nm}", dst)[0]:
                    got += 1
                elif os.path.exists(dst):
                    os.remove(dst)                # curl -f leaves empties
        except Exception as e:
            print(f"{p['name']}: {e}")
    print(f"harvested {got} files -> {OUT}")


def terminate():
    st = json.load(open(STATE))
    for p in st["pods"]:
        try:
            api("DELETE", f"/pods/{p['id']}")
            print(f"terminated {p['id']}")
        except RuntimeError as e:
            print(f"{p['id']}: {e}")
    live = api("GET", "/pods")
    running = [q for q in live if q.get("desiredStatus") == "RUNNING"]
    print(f"pods still RUNNING account-wide: {len(running)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "launch":
        launch(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
    elif cmd == "upload":
        upload()
    elif cmd == "harvest":
        harvest()
    elif cmd == "terminate":
        terminate()
    else:
        status()
