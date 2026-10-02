"""FIX-02 timing (BENCHMARK, report-only): per-call cost of token resolution, U vs F.

Runs inside ONE private X11 session with AT-SPI, under bin/quiet-timed (exclusive quiet-lane lock).
Blocks alternate U and F in the order given (default UFFUUFFUUF). Each block starts a fresh
`cua-driver mcp` (T1, one session label) and a fresh GTK3 TaskWindow fixture, then runs N pairs of
(get_window_state, click element_token "I agree"), timing each MCP tools/call on the client
(monotonic, request sent -> response parsed). The fixture state file confirms every click landed
(seq advanced); a pair whose click did not land is kept and flagged.

usage: timing.py --driver-u <bin> --driver-f <bin> --out <jsonl> [--order UFFUUFFUUF] [--pairs 20]
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpclient import McpClient  # noqa: E402

FIX = os.environ["OWN36_FIXTURE"]
WORK = os.environ["OWN36_WORK"]
PY = os.environ.get("OWN36_PYTHON", "python3")


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def read_state(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def block(arm, driver, index, pairs, out):
    state_path = os.path.join(WORK, f"timing-state-{index}.json")
    if os.path.exists(state_path):
        os.remove(state_path)
    env = dict(os.environ, CUA_GTK3_TASK_STATE=state_path)
    app = subprocess.Popen([PY, FIX], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and (read_state(state_path) or {}).get("pid") != app.pid:
            time.sleep(0.1)
        denv = dict(os.environ, DO_NOT_TRACK="1", CUA_DRIVER_RS_TELEMETRY_ENABLED="0")
        client = McpClient([driver, "mcp"], os.path.join(WORK, f"timing-{index}.stderr"), env=denv)
        client.initialize()
        label = f"fix02-timing-{index}"
        window = None
        for _ in range(75):
            r = client.call("list_windows", {"pid": app.pid, "session": label})
            w = (r.get("structuredContent") or {}).get("windows") or []
            if w:
                window = w[0]["window_id"]
                break
            time.sleep(0.2)
        la = open("/proc/loadavg").read().split()[:3]
        for pair in range(pairs):
            t0 = time.monotonic_ns()
            g = client.call("get_window_state", {"pid": app.pid, "window_id": window, "session": label})
            t1 = time.monotonic_ns()
            token = next((e.get("element_token") for e in (g.get("structuredContent") or {}).get("elements", [])
                          if e.get("label") == "I agree"), None)
            before = (read_state(state_path) or {}).get("seq")
            t2 = time.monotonic_ns()
            c = client.call("click", {"pid": app.pid, "element_token": token, "session": label})
            t3 = time.monotonic_ns()
            landed = False
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if (read_state(state_path) or {}).get("seq") != before:
                    landed = True
                    break
                time.sleep(0.01)
            out.write(json.dumps({
                "kind": "pair", "arm": arm, "block": index, "pair": pair, "loadavg_block": la,
                "gws_ms": round((t1 - t0) / 1e6, 3), "click_ms": round((t3 - t2) / 1e6, 3),
                "gws_error": bool(g.get("isError")) or "rpc_error" in g,
                "click_error": bool(c.get("isError")) or "rpc_error" in c,
                "click_landed": landed, "utc": utc()}) + "\n")
            out.flush()
        client.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver-u", required=True)
    ap.add_argument("--driver-f", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--order", default="UFFUUFFUUF")
    ap.add_argument("--pairs", type=int, default=20)
    args = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    drivers = {"U": args.driver_u, "F": args.driver_f}
    with open(args.out, "a", encoding="utf-8") as out:
        header = {"kind": "header", "display": os.environ.get("DISPLAY"), "order": args.order,
                  "pairs": args.pairs, "started_utc": utc(),
                  "drivers": {arm: {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
                                    "version": subprocess.run([p, "--version"], capture_output=True,
                                                              text=True).stdout.strip()}
                              for arm, p in drivers.items()}}
        out.write(json.dumps(header) + "\n")
        for index, arm in enumerate(args.order):
            block(arm, drivers[arm], index, args.pairs, out)
        out.write(json.dumps({"kind": "end", "ended_utc": utc()}) + "\n")


if __name__ == "__main__":
    main()
