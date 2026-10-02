"""Drive stack2-addr runs: one private X11 session per Hermes computer-use task run.

Adapted from the accepted SMOKE harness (../stack-smoke-2026-10-02/harness/drive.py): the prompts, the Hermes
config, the allowlist, the model, the fixtures and the oracle are unchanged. What changes is the arm: it selects the
Hermes build (before = exp/stack-integration-20261002 0d60437a, after = exp/stack-addr-20261002 with the
element-addressing fix). The observer plugin is present and enabled in every run (metadata only, as in the SMOKE
"on"/compat arm); no shadow sidecar runs.

usage: hostless python3 drive.py <lane.json> <plan.json> [--only RUN_ID ...]
lane.json (local, never committed) holds machine paths; plan.json lists runs:
  {"runs": [{"run_id", "task": "gtk3"|"browser", "arm": "before"|"after", "pair": int,
             "driver_key": "main_0_32_0"|"pinned_0_21_0", "set": "measured"|"legacy"|"pilot"}]}
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent

PROMPTS = {  # verbatim from the SMOKE harness
    "gtk3": (
        "A GTK test window titled 'CuaTestHarness GTK3 Tasks' is open on this desktop; its app name for "
        "computer_use is 'Main.py'. Task: check the checkbox labeled 'I agree' in that window and change nothing "
        "else. Use the computer_use tool and never pass pid or window_id: 1) action='capture' with mode='ax' and "
        "app='Main.py'; 2) action='click' with element=<index of the 'I agree' check box>; 3) action='capture' with "
        "mode='ax' and app='Main.py' to confirm it is checked; 4) reply with the single word DONE."
    ),
    "browser": (
        "A Chrome window is open on this desktop; its app name for computer_use is 'Google-chrome'. It shows a web "
        "form with a text field labeled 'verification value' and a Submit button. Task: enter the exact value "
        "{token} into that field and submit the form. Chrome only accepts input with delivery_mode='foreground'. "
        "Use the computer_use tool and never pass pid or window_id: 1) action='capture' with mode='ax' and "
        "app='Google-chrome'; in its 'elements' list find the element with role 'entry' and label 'verification "
        "value', and the element with role 'button' and label 'Submit'; 2) action='click' with element=<index of "
        "that entry> and delivery_mode='foreground'; 3) action='type' with text='{token}' and "
        "delivery_mode='foreground'; 4) action='click' with element=<index of that Submit button> and "
        "delivery_mode='foreground'; "
        "5) reply with the single word DONE."
    ),
}

ALLOWLIST = [  # verbatim from the SMOKE harness: explicit per-action grants; no yolo, Driver stays 'standard'
    "cua:click:background", "cua:click:foreground", "cua:type:background", "cua:type:foreground",
    "cua:key:background", "cua:key:foreground", "cua:set_value:background",
    "cua:scroll:background", "cua:scroll:foreground",
]


def token_for(pair: int) -> str:
    return f"adr{pair:02d}-" + hashlib.sha256(f"stack2-addr-2026-10-02/{pair}".encode()).hexdigest()[:6]


def config_yaml(model: str, base_url: str, observer: bool) -> str:  # verbatim from the SMOKE harness
    plugins = "    - z0-hermes-observer\n" if observer else ""
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
{plugins if plugins else '    []' + chr(10)}  auto_update_check_hours: 0
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


def prepare(lane: dict, run: dict) -> Path:
    rd = Path(lane["runs_dir"]) / run["run_id"]
    if rd.exists():
        raise SystemExit(f"run dir exists: {rd}")
    hermes = rd / "home" / ".hermes"
    (hermes / "plugins").mkdir(parents=True)
    for sub in (".config", ".cache", ".local/share", ".local/state"):
        (rd / "home" / sub).mkdir(parents=True, exist_ok=True)
    build = lane["hermes"][run["arm"]]
    os.symlink(Path(build["wt"]) / "lab" / "z0_hermes_observer", hermes / "plugins" / "z0-hermes-observer")
    (hermes / "config.yaml").write_text(config_yaml(lane["model"], lane["base_url"], True))
    token = token_for(run["pair"])
    prompt = PROMPTS[run["task"]].format(token=token)
    env = {
        "RUN": str(rd), "TASK": run["task"], "ARM": run["arm"], "PROMPT": prompt, "TOKEN": token,
        "DRIVER": lane["drivers"][run["driver_key"]], "HERMES_WT": build["wt"], "HERMES_VENV": build["venv"],
        "FIXTURE_GTK": lane["fixture_gtk"], "FIXTURE_SERVER": lane["fixture_server"],
        "HERMES_TIMEOUT": str(lane["hermes_timeout"]), "MAX_TURNS": str(lane["max_turns"]),
        "LIVE_HERMES_HOME": lane["live_hermes_home"], "REAL_HOME": lane["real_home"], "STABLE": lane["stable_dir"],
    }
    (rd / "run.env").write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in env.items()))
    (rd / "run.json").write_text(json.dumps({**run, "token": token, "hermes_head": build["head"],
                                             "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
                                            indent=1, sort_keys=True))
    return rd


def server_state(base_url: str) -> dict:
    """Model-server residency at run start (other lanes may share the server; recorded, never controlled)."""
    root = base_url.rsplit("/v1", 1)[0]
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ps = json.loads(opener.open(root + "/api/ps", timeout=5).read().decode())
        return {"loaded": [{"name": m.get("name"), "digest": (m.get("digest") or "")[:12],
                            "context_length": m.get("context_length"), "size_vram": m.get("size_vram")}
                           for m in ps.get("models", [])]}
    except Exception as e:  # recorded, never fatal
        return {"error": f"{type(e).__name__}: {e}"}


def execute(lane: dict, run: dict) -> dict:
    rd = prepare(lane, run)
    env = {k: v for k, v in os.environ.items()}
    env["CUA_SESSION_ATSPI"] = "1"
    env["CUA_SESSION_EXTRA_ENV"] = f"CUA_SESSION_ATSPI=1 SMOKE_ENV={rd / 'run.env'}"
    t0 = time.time()
    with open(rd / "session.log", "wb") as log:
        p = subprocess.run([lane["x11_session"], str(H / "run_one.sh")], cwd=str(rd), env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=lane["hermes_timeout"] + 600)
    oracle = json.loads((rd / "oracle.json").read_text()) if (rd / "oracle.json").exists() else {"verdict": "unknown"}
    rc = (rd / "meta" / "exit_code").read_text().strip() if (rd / "meta" / "exit_code").exists() else None
    return {"run_id": run["run_id"], "session_rc": p.returncode, "hermes_rc": rc, "oracle": oracle.get("verdict"),
            "wall_s": round(time.time() - t0, 1)}


def main() -> None:
    lane = json.loads(Path(sys.argv[1]).read_text())
    plan = json.loads(Path(sys.argv[2]).read_text())
    only = set(sys.argv[sys.argv.index("--only") + 1:]) if "--only" in sys.argv else None
    ledger = Path(lane["runs_dir"]) / "drive-ledger.jsonl"
    for run in plan["runs"]:
        if only and run["run_id"] not in only:
            continue
        if (Path(lane["runs_dir"]) / run["run_id"]).exists():
            print("skip existing", run["run_id"], flush=True)
            continue
        started = time.time()
        srv = server_state(lane["base_url"])
        load1 = os.getloadavg()[0]
        try:
            res = execute(lane, run)
        except Exception as e:  # harness failure is recorded, never dropped
            res = {"run_id": run["run_id"], "harness_error": f"{type(e).__name__}: {e}"}
        res.update(started=started, server_at_start=srv, loadavg1_at_start=round(load1, 2))
        with ledger.open("a") as fh:
            fh.write(json.dumps(res, sort_keys=True) + "\n")
        print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
