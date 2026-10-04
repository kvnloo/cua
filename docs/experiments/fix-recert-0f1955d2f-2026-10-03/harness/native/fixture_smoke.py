"""RECERT-FIX Part B fixture smoke (new). Run inside cua-x11-session.sh with AT-SPI, under hostless.

usage: fixture_smoke.py --driver <bin> --base-fixture <file> --new-fixture <file> --out <jsonl> --work <dir>

Default-off check: the base fixture (upstream blob) and the new fixture WITHOUT CUA_GTK3_TWO_WINDOWS
are each launched in task mode; for each, the Driver lists the process's windows and observes the
task window. PASS iff both show exactly one window with the same title, the same state-file keys and
schema, and the same (role, label) element sequence. Variant check: the new fixture WITH
CUA_GTK3_TWO_WINDOWS=1 lists exactly two windows titled "... Tasks 1" / "... Tasks 2" of ONE pid,
each observation has its own "I agree" checkbox, and the state file has window1/window2 entries.
Plain launches (no task state) are also compared: one HarnessWindow each.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpclient import McpClient  # noqa: E402


def launch(fixture, work, tag, env_extra):
    state = os.path.join(work, f"state-{tag}.json")
    if os.path.exists(state):
        os.remove(state)
    env = dict(os.environ, **env_extra)
    if "CUA_GTK3_TASK_STATE" in env_extra:
        env["CUA_GTK3_TASK_STATE"] = state
    proc = subprocess.Popen([os.environ.get("OWN36_PYTHON", "python3"), fixture], env=env,
                            stdout=open(os.path.join(work, f"app-{tag}.log"), "ab"), stderr=subprocess.STDOUT)
    return proc, state


def read(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def windows_of(client, pid, want, timeout=15):
    deadline = time.monotonic() + timeout
    windows = []
    while time.monotonic() < deadline:
        result = client.call("list_windows", {"pid": pid})
        windows = (result.get("structuredContent") or {}).get("windows") or []
        if len(windows) >= want:
            time.sleep(1.0)  # let a late second window appear before deciding
            result = client.call("list_windows", {"pid": pid})
            return (result.get("structuredContent") or {}).get("windows") or []
        time.sleep(0.2)
    return windows


def shape(client, pid, window):
    result = client.call("get_window_state", {"pid": pid, "window_id": window["window_id"]})
    sc = result.get("structuredContent") or {}
    return [(e.get("role"), e.get("label")) for e in sc.get("elements", [])]


def probe(client, fixture, work, tag, env_extra, want):
    proc, state_path = launch(fixture, work, tag, env_extra)
    try:
        time.sleep(1.5)
        windows = windows_of(client, proc.pid, want)
        rec = {"tag": tag, "pid": proc.pid, "env": sorted(env_extra),
               "windows": [{"title": w.get("title")} for w in windows],
               "elements": [shape(client, proc.pid, w) for w in windows]}
        state = read(state_path) if "CUA_GTK3_TASK_STATE" in env_extra else None
        if state is not None:
            rec["state_schema"] = state.get("schema")
            rec["state_keys"] = sorted(state)
            rec["state_pid_matches"] = state.get("pid") == proc.pid
            if "windows" in state:
                rec["state_window_keys"] = sorted(state["windows"])
                rec["state_window_fields"] = {k: sorted(v) for k, v in state["windows"].items()}
        return rec
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", required=True)
    ap.add_argument("--base-fixture", required=True)
    ap.add_argument("--new-fixture", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    env = dict(os.environ, DO_NOT_TRACK="1", CUA_DRIVER_RS_TELEMETRY_ENABLED="0")
    client = McpClient([args.driver, "mcp"], os.path.join(args.work, "mcp.stderr"), env=env)
    client.initialize()
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    out = {"kind": "fixture_smoke", "driver_sha256": sha(args.driver),
           "driver_version": subprocess.run([args.driver, "--version"], capture_output=True, text=True,
                                            env=env).stdout.strip(),
           "base_fixture_sha256": sha(args.base_fixture), "new_fixture_sha256": sha(args.new_fixture),
           "display": os.environ.get("DISPLAY"), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    task = {"CUA_GTK3_TASK_STATE": "x"}
    out["base_task"] = probe(client, args.base_fixture, args.work, "base-task", task, 1)
    out["new_task_default"] = probe(client, args.new_fixture, args.work, "new-task", task, 1)
    out["base_plain"] = probe(client, args.base_fixture, args.work, "base-plain", {}, 1)
    out["new_plain_default"] = probe(client, args.new_fixture, args.work, "new-plain", {}, 1)
    out["new_two_windows"] = probe(client, args.new_fixture, args.work, "new-two",
                                   dict(task, CUA_GTK3_TWO_WINDOWS="1"), 2)
    client.close()
    b, n = out["base_task"], out["new_task_default"]
    checks = {
        "default_task_one_window": len(b["windows"]) == 1 and len(n["windows"]) == 1,
        "default_task_same_title": b["windows"] == n["windows"],
        "default_task_same_state_keys": b.get("state_keys") == n.get("state_keys")
        and b.get("state_schema") == n.get("state_schema") == "cua.gtk3_task_state_v1",
        "default_task_same_elements": b["elements"] == n["elements"],
        "default_plain_same": out["base_plain"]["windows"] == out["new_plain_default"]["windows"]
        and out["base_plain"]["elements"] == out["new_plain_default"]["elements"]
        and len(out["base_plain"]["windows"]) == 1,
    }
    t = out["new_two_windows"]
    titles = sorted(w["title"] for w in t["windows"])
    checks["two_windows_listed"] = titles == ["CuaTestHarness GTK3 Tasks 1", "CuaTestHarness GTK3 Tasks 2"]
    checks["two_windows_each_checkbox"] = len(t["elements"]) == 2 and all(
        sum(1 for role, label in els if label == "I agree") == 1 for els in t["elements"])
    checks["two_windows_state"] = (t.get("state_schema") == "cua.gtk3_two_window_task_state_v1"
                                   and t.get("state_window_keys") == ["window1", "window2"]
                                   and t.get("state_pid_matches") is True)
    out["checks"] = checks
    out["pass"] = all(checks.values())
    with open(args.out, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(out, sort_keys=True) + "\n")
    print(json.dumps({"pass": out["pass"], "checks": checks}))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
