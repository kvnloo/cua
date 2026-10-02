"""Collect the CONFIRM frozen sample set: every task in tasks.jsonl order, one isolated Hermes turn per task.

usage: hostless python3 drive.py <lane.json> <tasks.jsonl> <fixtures_dir> <collect_dir> <deadline ISO8601Z> [--prefix P]

Per task: prepare a fresh private run dir (Hermes home with the ADDR/SMOKE profile, observer plugin on), run
run_task.sh (file tasks directly, under this hostless process; CUA tasks inside a fresh cua-x11-session.sh),
then the independent fixture oracle (workload.py oracle). Appends collect_dir/index.jsonl and verdicts.jsonl.
Stop rule (PREREG): strict file order, one at a time; no task starts after the deadline (NOT_RUN); no task is
re-run, skipped or dropped after its outcome is seen. A harness failure is recorded on the task's row.
lane.json (local, never committed) holds machine paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

H = Path(__file__).resolve().parent

ALLOWLIST = [  # verbatim from the SMOKE/ADDR harness: explicit per-action grants; no yolo, Driver stays 'standard'
    "cua:click:background", "cua:click:foreground", "cua:type:background", "cua:type:foreground",
    "cua:key:background", "cua:key:foreground", "cua:set_value:background",
    "cua:scroll:background", "cua:scroll:foreground",
]


def config_yaml(model: str, base_url: str) -> str:  # verbatim from the SMOKE/ADDR harness (observer on)
    allow = "".join(f"  - \"{k}\"\n" for k in ALLOWLIST)
    return f"""# stack-smoke private Hermes profile (generated per run; local model only).
model:
  default: "{model}"
  provider: "custom"
  base_url: "{base_url}"
  api_key: "ollama-local-no-key"
  context_length: 65536
  ollama_num_ctx: 65536
plugins:
  enabled:
    - z0-hermes-observer
  auto_update_check_hours: 0
  auto_apply: false
updates:
  check: false
  refresh_cua_driver: false
  pre_update_backup: "off"
model_catalog:
  enabled: false
computer_use:
  cua_telemetry: false
  permission_mode: "standard"
  autostart: false
  native_wayland: false
  capture_after_mode: "ax"
bot_desktop:
  auto_start: false
tools:
  tool_search:
    enabled: "off"   # expose computer_use directly (no tool_search/tool_call bridge) to the local model
command_allowlist:
{allow}logging:
  level: "INFO"
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def server_state(base_url: str) -> dict:
    """Model-server residency at run start (recorded, never controlled)."""
    root = base_url.rsplit("/v1", 1)[0]
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ps = json.loads(opener.open(root + "/api/ps", timeout=5).read().decode())
        return {"loaded": [{"name": m.get("name"), "digest": (m.get("digest") or "")[:12],
                            "context_length": m.get("context_length"), "size_vram": m.get("size_vram")}
                           for m in ps.get("models", [])]}
    except Exception as e:  # recorded, never fatal
        return {"error": f"{type(e).__name__}: {e}"}


def prepare(lane: dict, task: dict, run_id: str, fixtures: Path) -> Path:
    rd = Path(lane["runs_dir"]) / run_id
    if rd.exists():
        raise RuntimeError(f"run dir exists: {rd}")
    hermes = rd / "home" / ".hermes"
    (hermes / "plugins").mkdir(parents=True)
    for sub in (".config", ".cache", ".local/share", ".local/state"):
        (rd / "home" / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("meta", "cwd", "tmp", "fixture"):
        (rd / sub).mkdir(parents=True, exist_ok=True)
    os.symlink(Path(lane["hermes_wt"]) / "lab" / "z0_hermes_observer", hermes / "plugins" / "z0-hermes-observer")
    (hermes / "config.yaml").write_text(config_yaml(lane["model"], lane["base_url"]))
    src = fixtures / task["task_id"]
    if src.is_dir():
        shutil.copytree(src, rd / "cwd", dirs_exist_ok=True)
    env = {
        "RUN": str(rd), "KIND": task["kind"], "APP": task["app"], "DENSITY": task["density"],
        "TOOLSET": task["toolset"], "MAX_TURNS": str(task["max_turns"]), "PROMPT": task["prompt"],
        "DRIVER": lane["driver"], "HERMES_VENV": lane["hermes_venv"], "FIXTURE_GTK": lane["fixture_gtk"],
        "FIXTURE_SERVER": lane["fixture_server"],
        "HERMES_TIMEOUT": str(lane["timeout_cua"] if task["kind"] == "cua" else lane["timeout_file"]),
        "LIVE_HERMES_HOME": lane["live_hermes_home"], "REAL_HOME": lane["real_home"], "STABLE": lane["stable_dir"],
        "MASK_DIRS": " ".join(lane["mask_dirs"]),
    }
    (rd / "run.env").write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in env.items()))
    head = subprocess.run(["git", "-C", lane["hermes_wt"], "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", lane["hermes_wt"], "status", "--porcelain"], capture_output=True, text=True).stdout
    (rd / "meta" / "worktree-head").write_text(head + "\n")
    (rd / "meta" / "worktree-status").write_text(dirty)
    (rd / "run.json").write_text(json.dumps({"run_id": run_id, "task_id": task["task_id"], "kind": task["kind"],
                                             "family": task["family"], "hermes_head": head,
                                             "prompt_sha256": hashlib.sha256(task["prompt"].encode()).hexdigest()},
                                            indent=1, sort_keys=True))
    return rd


def session_id(rd: Path) -> str | None:
    for name in ("stdout", "stderr"):
        try:
            m = re.search(r"^session_id:\s*(\S+)", (rd / "meta" / name).read_text(errors="replace"), re.M)
        except FileNotFoundError:
            continue
        if m:
            return m.group(1)
    return None


def execute(lane: dict, task: dict, rd: Path) -> int:
    env = dict(os.environ)
    env["CONFIRM_ENV"] = str(rd / "run.env")
    with open(rd / "session.log", "wb") as log:
        if task["kind"] == "cua":
            env["CUA_SESSION_ATSPI"] = "1"
            env["CUA_SESSION_EXTRA_ENV"] = f"CUA_SESSION_ATSPI=1 CUA_HOSTLESS=1 CONFIRM_ENV={rd / 'run.env'}"
            cmd = [lane["x11_session"], str(H / "run_task.sh")]
            limit = lane["timeout_cua"] + 600
        else:
            cmd = ["bash", str(H / "run_task.sh")]
            limit = lane["timeout_file"] + 120
        p = subprocess.run(cmd, cwd=str(rd), env=env, stdout=log, stderr=subprocess.STDOUT, timeout=limit,
                           stdin=subprocess.DEVNULL)
    return p.returncode


def main() -> None:
    lane = json.loads(Path(sys.argv[1]).read_text())
    tasks_path, fixtures, out = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    deadline = datetime.fromisoformat(sys.argv[5].replace("Z", "+00:00")).timestamp()
    prefix = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else "M"
    out.mkdir(parents=True, exist_ok=True)
    tasks = [json.loads(l) for l in tasks_path.read_text().splitlines() if l.strip()]
    done = set()
    if (out / "index.jsonl").exists():
        done = {json.loads(l)["task_id"] for l in (out / "index.jsonl").read_text().splitlines() if l.strip()}
    for task in tasks:
        tid = task["task_id"]
        if tid in done:
            continue
        if time.time() >= deadline:
            row = {"task_id": tid, "status": "NOT_RUN", "reason": "deadline"}
            with (out / "index.jsonl").open("a") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            continue
        run_id = f"{prefix}-{tid}"
        srv = server_state(lane["base_url"])
        load1 = os.getloadavg()[0]
        t0 = now()
        rc, harness_error, rd = None, None, Path(lane["runs_dir"]) / run_id
        try:
            rd = prepare(lane, task, run_id, fixtures)
            rc = execute(lane, task, rd)
        except Exception as e:  # recorded on the row, never dropped
            harness_error = f"{type(e).__name__}: {e}"
        t1 = now()
        try:
            hrc = int((rd / "meta" / "exit_code").read_text().strip())
        except (FileNotFoundError, ValueError):
            hrc = None
        sid = session_id(rd)
        try:
            verdict = json.loads(subprocess.run([sys.executable, str(H / "workload.py"), "oracle", str(tasks_path),
                                                 str(rd), tid], capture_output=True, text=True, check=True,
                                                stdin=subprocess.DEVNULL).stdout)
        except Exception as e:
            verdict = {"task_id": tid, "verified_success": None, "oracle_error": f"{type(e).__name__}: {e}"}
        with (out / "verdicts.jsonl").open("a") as fh:
            fh.write(json.dumps(verdict, sort_keys=True) + "\n")
        row = {"task_id": tid, "run_id": run_id, "kind": task["kind"], "family": task["family"], "status": "RUN",
               "exit_code": hrc, "session_rc": rc, "harness_error": harness_error, "session_id": sid,
               "started_at": t0, "ended_at": t1, "server_at_start": srv, "loadavg1_at_start": round(load1, 2)}
        with (out / "index.jsonl").open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        print(json.dumps({"task_id": tid, "rc": hrc, "verdict": verdict.get("verified_success"),
                          "wall_s": round(datetime.fromisoformat(t1[:-1]).timestamp() - datetime.fromisoformat(t0[:-1]).timestamp(), 1)}),
              flush=True)
    print(f"drive: done {now()}", flush=True)


if __name__ == "__main__":
    main()
