#!/usr/bin/env python3
"""OWN-78 cell harness: unmodified PR 4394 runners + real Driver + Chrome, target-owned oracle.

Run only inside cua-x11-session.sh (refuses otherwise). One invocation runs one block of at most
10 cells sequentially; the caller holds the quiet-lane lock (shared) around the session.

Cells are "<row>:<runtime>" with row in R1 R2 R3 R4 and runtime in py ts:
  R1  --provider typesafe, stock fixture, live TypeSafe
  R2  --provider mock, stock fixture, TYPESAFE_API_KEY removed from the runner env
  R3  --provider typesafe, TYPESAFE_BASE_URL = closed loopback port from the start, journal fixture
  R4  --provider typesafe, journal fixture, OWN78_SWITCH_BASE_URL = closed loopback port
      (launcher switches the base URL after the first ok browser_type)
  S2  smoke only: --provider mock on the journal fixture (checks the journal counting, no provider)
  R4s (amendment 1) R4 with the first decision answered by a loopback TypeSafe-wire stub, dummy key
  R0  (amendment 1) pre-PR runner at base (--examples points at the base worktree), --provider live

usage: own78_harness.py --phase <name> --cells R1:py,R1:ts,... --examples <wt>/libs/cua-driver/examples/jev-use
         --driver <bin> --driver-sha256 <sha256> --tested-sha <sha> --out <dir> --budget-file <json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
PY_LAUNCHER = HERE / "receipt_launcher.py"
TS_PRELOAD = HERE / "ts_receipts.mjs"
LANE_CAP_REACHED = 45
EXPECTED_REACHED = {"R1": 2, "R2": 0, "R3": 0, "R4": 1, "S2": 0, "R4s": 0, "R0": 2}
DUMMY_KEY = "own78-dummy-key-not-a-secret"
MAX_CELLS_PER_BLOCK = 10
CELL_TIMEOUT_S = 180
FORBIDDEN_ENV = (
    "CUA_DRIVER_PERMISSION_MODE",
    "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
    "CUA_E2E_BROWSER_NO_SANDBOX",
    "WAYLAND_DISPLAY",
    "HYPRLAND_INSTANCE_SIGNATURE",
)

JOURNAL_SCRIPT = (
    b"<script>(()=>{const f=document.querySelector('input[name=\"value\"]');let n=0;"
    b"f.addEventListener('input',(e)=>{n+=1;fetch('/event/input',{method:'POST',"
    b"headers:{'Content-Type':'application/json'},body:JSON.stringify({seq:n,value:f.value,"
    b"trusted:e.isTrusted,input_type:e.inputType||null}),keepalive:true}).catch(()=>{});});})();"
    b"</script>"
)


def now() -> int:
    return time.monotonic_ns()


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def loadavg() -> list[str]:
    return Path("/proc/loadavg").read_text().split()[:3]


def closed_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"unparsed_line": True})
    return out


def session_pids(xdg_runtime: str) -> dict[int, str]:
    """Live processes carrying this isolated session's XDG_RUNTIME_DIR (all started in this session)."""
    needle = f"XDG_RUNTIME_DIR={xdg_runtime}".encode()
    found: dict[int, str] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            if needle in Path(f"/proc/{entry}/environ").read_bytes().split(b"\0"):
                found[int(entry)] = Path(f"/proc/{entry}/comm").read_text().strip()
        except OSError:
            continue
    return found


def make_server(examples: Path, *, journal: bool, token: str):
    sys.path.insert(0, str(examples))
    import fixture_server
    from fixture_server import FixtureHandler, FixtureServer

    page = fixture_server.PAGE.replace(b"</form>", b"</form>" + JOURNAL_SCRIPT) if journal else None
    if journal:
        assert page != fixture_server.PAGE

    class CountingHandler(FixtureHandler):
        def do_GET(self) -> None:  # noqa: N802
            srv = self.server
            with srv.lock:
                srv.counts[f"GET {self.path}"] = srv.counts.get(f"GET {self.path}", 0) + 1
            if journal and self.path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", page)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            srv = self.server
            with srv.lock:
                srv.counts[f"POST {self.path}"] = srv.counts.get(f"POST {self.path}", 0) + 1
            if journal and self.path == "/event/input":
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length).decode() or "{}")
                except ValueError:
                    body = {}
                value = body.get("value") if isinstance(body.get("value"), str) else ""
                entry = {
                    "seq": body.get("seq") if isinstance(body.get("seq"), int) else None,
                    "arrival_ns": now(),
                    "length": len(value),
                    "equals_token": value == token,
                    "trusted": body.get("trusted") if isinstance(body.get("trusted"), bool) else None,
                    "input_type": body.get("input_type") if isinstance(body.get("input_type"), str) else None,
                }
                with srv.lock:
                    srv.journal.append(entry)
                self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
                return
            if self.path == "/submit":
                with srv.lock:
                    srv.submit_ns.append(now())
            super().do_POST()

    class CountingServer(FixtureServer):
        def __init__(self, address):
            self.lock = threading.Lock()
            self.counts: dict[str, int] = {}
            self.journal: list[dict] = []
            self.submit_ns: list[int] = []
            super().__init__(address)
            self.RequestHandlerClass = CountingHandler

    return CountingServer(("127.0.0.1", 0))


class StubServer:
    """Loopback stand-in speaking the TypeSafe /v1/systemone wire format (R4s only).

    Records only request count, question names, criteria ids, the chosen id and whether an
    Authorization header was present; never header values or bodies.
    """

    def __init__(self) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        stub = self
        self.log: list[dict] = []
        self.lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                if self.path != "/v1/systemone":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                try:
                    body = json.loads(raw.decode() or "{}")
                except ValueError:
                    body = {}
                questions = body.get("questions") if isinstance(body.get("questions"), dict) else {}
                answers, record = {}, {"arrival_ns": now(), "auth_header_present": bool(self.headers.get("Authorization")), "questions": {}}
                for name, question in questions.items():
                    criteria = list((question or {}).get("criteria") or {})
                    choice = next((c for c in ("type-verification-value", "submit-form", "abstain") if c in criteria), None)
                    if choice is None:
                        continue
                    rest = [c for c in criteria if c != choice]
                    probabilities = {c: (0.9 if c == choice else round(0.1 / len(rest), 6)) for c in criteria} if rest else {choice: 1.0}
                    answers[name] = {"type": "choice", "choice": choice, "confidence": 0.9 if rest else 1.0, "probabilities": probabilities}
                    record["questions"][name] = {"criteria_ids": criteria, "chosen": choice}
                with stub.lock:
                    record["n"] = len(stub.log) + 1
                    stub.log.append(record)
                payload = json.dumps({"model": "own78-loopback-stub", "usage": {"input_tokens": 0, "output_tokens": 0}, "answers": answers}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("x-typesafe-request-id", f"own78-stub-{record['n']}")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> list[dict]:
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            return list(self.log)


class Budget:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = (
            json.loads(path.read_text())
            if path.exists()
            else {"lane_cap_reached": LANE_CAP_REACHED, "attempts": 0, "reached": 0, "guard_refused": 0, "by_cell": {}}
        )

    def can_start(self, row: str) -> bool:
        return self.data["reached"] + EXPECTED_REACHED[row] <= LANE_CAP_REACHED

    def allowance(self) -> int:
        return max(0, LANE_CAP_REACHED - self.data["reached"])

    def add(self, cell_id: str, attempts: int, reached: int, refused: int) -> None:
        self.data["attempts"] += attempts
        self.data["reached"] += reached
        self.data["guard_refused"] += refused
        self.data["by_cell"][cell_id] = {"attempts": attempts, "reached": reached, "guard_refused": refused}
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")


def run_cell(args, out: Path, budget: Budget, *, phase: str, index: int, row: str, runtime: str) -> dict:
    cell_id = f"{phase}-{index:02d}-{row}-{runtime}"
    token = f"own78-{phase}-{index:02d}-{row.lower()}-{runtime}"
    cdir = out / "cells" / cell_id
    cdir.mkdir(parents=True, exist_ok=False)
    log_path, receipts_path = cdir / "runner.jsonl", cdir / "receipts.jsonl"
    journal = row in ("R3", "R4", "S2", "R4s")
    server = make_server(args.examples, journal=journal, token=token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"

    provider = "mock" if row in ("R2", "S2") else "live" if row == "R0" else "typesafe"
    common = ["--provider", provider, "--fixture-url", url, "--token", token, "--max-steps", "4", "--log", str(log_path)]
    if runtime == "py":
        cmd = [str(args.examples / ".venv/bin/python"), str(PY_LAUNCHER), str(args.examples), *common]
    else:
        cmd = ["node", "--import", "tsx", "--import", TS_PRELOAD.as_uri(), "typescript/run.ts", *common]
    env = dict(os.environ)
    env.pop("TYPESAFE_BASE_URL", None)
    env["CUA_DRIVER_BIN"] = str(args.driver)
    env["OWN78_RECEIPT_LOG"] = str(receipts_path)
    env["OWN78_FIXTURE_ORIGIN"] = url
    closed = None
    stub = None
    if row in ("R2", "S2"):
        env.pop("TYPESAFE_API_KEY", None)
        env["OWN78_PROVIDER_REACH_ALLOWANCE"] = "0"
    elif row == "R3":
        closed = f"http://127.0.0.1:{closed_loopback_port()}"
        env["TYPESAFE_BASE_URL"] = closed
        env["OWN78_PROVIDER_REACH_ALLOWANCE"] = "0"
    elif row == "R4s":
        stub = StubServer()
        env["TYPESAFE_BASE_URL"] = stub.url
        env["TYPESAFE_API_KEY"] = DUMMY_KEY
        env["OWN78_PROVIDER_REACH_ALLOWANCE"] = "0"
        closed = f"http://127.0.0.1:{closed_loopback_port()}"
        env["OWN78_SWITCH_BASE_URL"] = closed
    else:
        env["OWN78_PROVIDER_REACH_ALLOWANCE"] = str(budget.allowance())
        if row == "R4":
            closed = f"http://127.0.0.1:{closed_loopback_port()}"
            env["OWN78_SWITCH_BASE_URL"] = closed

    xdg = os.environ["XDG_RUNTIME_DIR"]
    before = session_pids(xdg)
    cell = {
        "cell_id": cell_id, "phase": phase, "index": index, "row": row, "runtime": runtime,
        "provider_flag": provider, "fixture": "journal_variant" if journal else "stock", "token": token,
        "closed_port_used": closed is not None, "loadavg_at_spawn": loadavg(),
        "key_in_runner_env": bool(env.get("TYPESAFE_API_KEY", "").strip()) and env.get("TYPESAFE_API_KEY") != DUMMY_KEY,
        "dummy_key_in_runner_env": env.get("TYPESAFE_API_KEY") == DUMMY_KEY,
        "stub_used": stub is not None,
        "allowance": env.get("OWN78_PROVIDER_REACH_ALLOWANCE"),
    }
    with (cdir / "stdout.txt").open("wb") as stdout_f, (cdir / "stderr.txt").open("wb") as stderr_f:
        spawn_ns = now()
        proc = subprocess.Popen(cmd, cwd=args.examples, env=env, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
        timed_out = False
        try:
            rc = proc.wait(timeout=CELL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, 15)
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, 9)
                rc = proc.wait()
        exit_ns = now()
    time.sleep(0.6)  # let in-flight page journal posts land before reading the oracle
    final_state = None
    try:
        with urlopen(url + "state", timeout=2) as response:
            final_state = json.load(response)
    except Exception as error:
        cell["final_state_error"] = type(error).__name__
    with server.lock:
        counts = dict(server.counts)
        journal_entries = list(server.journal)
        submit_ns = list(server.submit_ns)
    server.shutdown()
    server.server_close()
    stub_log = stub.close() if stub is not None else []

    time.sleep(0.5)
    leftovers = {pid: comm for pid, comm in session_pids(xdg).items() if pid not in before and pid != os.getpid()}
    killed = []
    for pid, comm in leftovers.items():  # started by this cell only; only browser/Driver/runner leftovers
        if not comm.startswith(("chrome", "cua-driver", "python", "node")):
            continue
        try:
            os.kill(pid, 9)
            killed.append(comm)
        except OSError:
            pass

    receipts = read_jsonl(receipts_path)
    attempts = [r for r in receipts if r.get("kind") == "http_attempt" and not r.get("guard_refused")]
    reached = [r for r in attempts if not r.get("loopback") and isinstance(r.get("status"), int)]
    refused = [r for r in receipts if r.get("kind") == "http_attempt" and r.get("guard_refused")]
    cell.update(
        {
            "rc": rc, "timed_out": timed_out, "spawn_ns": spawn_ns, "exit_ns": exit_ns,
            "final_state": final_state, "server_counts": counts, "submit_ns": submit_ns,
            "loadavg_at_exit": loadavg(), "leftover_processes_killed": sorted(killed),
            "http_attempts": len(attempts), "http_reached": len(reached), "guard_refused": len(refused),
        }
    )
    budget.add(cell_id, len(attempts), len(reached), len(refused))
    (cdir / "cell.json").write_text(json.dumps(cell, indent=1, sort_keys=True) + "\n")
    with (cdir / "trial.jsonl").open("w", encoding="utf-8") as raw:
        raw.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        for event in read_jsonl(log_path):
            raw.write(json.dumps({"type": "runner_event", "event": event}, sort_keys=True) + "\n")
        for receipt in receipts:
            raw.write(json.dumps({"type": "receipt", **receipt}, sort_keys=True) + "\n")
        for entry in journal_entries:
            raw.write(json.dumps({"type": "journal", **entry}, sort_keys=True) + "\n")
        for entry in stub_log:
            raw.write(json.dumps({"type": "stub", **entry}, sort_keys=True) + "\n")
    return cell


def validity(args) -> dict:
    examples_rel = "libs/cua-driver/examples/jev-use"
    worktree = args.examples.parents[2]
    git = lambda *a: subprocess.run(["git", "-C", str(worktree), *a], capture_output=True, text=True, check=True).stdout.strip()  # noqa: E731
    diff = git("diff", "--name-only", args.tested_sha, "--", examples_rel, "libs/cua-driver/rust")
    untracked = git("ls-files", "--others", "--exclude-standard", "--", examples_rel)
    result = {
        "head": git("rev-parse", "HEAD"),
        "tested_sha": args.tested_sha,
        "examples_and_rust_identical_to_tested_sha": diff == "" and untracked == "",
        "driver_sha256": sha256_file(args.driver),
        "driver_sha256_expected": args.driver_sha256,
        "forbidden_env_present": [name for name in FORBIDDEN_ENV if name in os.environ],
        "display_set": bool(os.environ.get("DISPLAY")),
        "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
        "typesafe_base_url_preset": "TYPESAFE_BASE_URL" in os.environ,
        "py_launcher_sha256": sha256_file(PY_LAUNCHER),
        "ts_preload_sha256": sha256_file(TS_PRELOAD),
        "harness_sha256": sha256_file(Path(__file__)),
        "fixture_server_sha256": sha256_file(args.examples / "fixture_server.py"),
        "run_py_sha256": sha256_file(args.examples / "python/run.py"),
        "run_ts_sha256": sha256_file(args.examples / "typescript/run.ts"),
        "browser_provider_py_sha256": sha256_file(args.examples / "python/browser_provider.py"),
        "browser_provider_ts_sha256": sha256_file(args.examples / "typescript/browser_provider.ts"),
        "python": sys.version.split()[0],
        "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
    }
    result["ok"] = (
        result["examples_and_rust_identical_to_tested_sha"]
        and result["driver_sha256"] == args.driver_sha256
        and not result["forbidden_env_present"]
        and result["display_set"]
        and not result["typesafe_base_url_preset"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--cells", required=True)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-file", type=Path, required=True)
    args = parser.parse_args()
    args.examples = args.examples.resolve()
    plan = [tuple(item.split(":")) for item in args.cells.split(",") if item]
    if len(plan) > MAX_CELLS_PER_BLOCK:
        print(json.dumps({"event": "refused", "reason": "more than 10 cells per lock acquisition"}))
        return 4
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    check = validity(args)
    check.update({"phase": args.phase, "plan": [f"{r}:{t}" for r, t in plan], "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "loadavg_at_start": loadavg()})
    (out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "key_present": check["typesafe_key_present"]}), flush=True)
    if not check["ok"]:
        return 2
    if any(row in ("R1", "R3", "R4", "R0") for row, _ in plan) and not check["typesafe_key_present"]:
        print(json.dumps({"event": "blocked", "reason": "TYPESAFE_API_KEY absent in session"}), flush=True)
        return 3
    budget = Budget(args.budget_file)
    cells_log = (out / "cells.jsonl").open("a", encoding="utf-8")
    stopped = None
    for index, (row, runtime) in enumerate(plan, start=1):
        if not budget.can_start(row):
            stopped = f"lane provider cap: {budget.data['reached']} reached of {LANE_CAP_REACHED}"
            break
        started = time.monotonic()
        try:
            cell = run_cell(args, out, budget, phase=args.phase, index=index, row=row, runtime=runtime)
        except Exception as error:  # a broken cell is data
            cell = {"cell_id": f"{args.phase}-{index:02d}-{row}-{runtime}", "phase": args.phase, "row": row,
                    "runtime": runtime, "harness_error": f"{type(error).__name__}: {error}"}
        cells_log.write(json.dumps(cell, sort_keys=True) + "\n")
        cells_log.flush()
        print(json.dumps({
            "event": "cell", "id": cell["cell_id"], "rc": cell.get("rc"), "state": cell.get("final_state"),
            "attempts": cell.get("http_attempts"), "reached": cell.get("http_reached"),
            "lane_reached": budget.data["reached"], "counts": cell.get("server_counts"),
            "wall_s": round(time.monotonic() - started, 1), "error": cell.get("harness_error"),
        }, sort_keys=True), flush=True)
        time.sleep(0.3)
    (out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stopped_early": stopped,
        "lane_reached_after": budget.data["reached"], "lane_attempts_after": budget.data["attempts"],
        "loadavg_at_end": loadavg(),
    }, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
