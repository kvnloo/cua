#!/usr/bin/env python3
"""OWN-78A cell harness: jev-use Python runner + real Driver + Chrome + target-owned fixture oracle.

Run only inside cua-x11-session.sh (refuses otherwise). One invocation runs one block of at most 10
cells sequentially; the caller holds the quiet-lane lock (shared) around the session.

Cells (arm codes):
  A0  PR runner (039257811) as-is, --provider typesafe, --dry-run --max-steps 1
  A1  PR runner + launcher seam OWN78A_SEAM_ADD_FORM=1 (adds observation.form only), same flags
  A2  F runner (fix candidate, = PR + form + page + outline), --provider typesafe, same flags
  A3  pre-PR runner (2ca90d338), --provider live, same flags
  C   F runner end to end (R1-lite), --provider typesafe, --max-steps 2 (at most 2 decisions)
With --stub every cell talks to a loopback stub that speaks the TypeSafe wire format (dummy
non-secret key, 0 provider requests); used for the smoke only.

Budget: lane cap 24 reached / 30 attempts (raw/budget.json across blocks). A cell starts only if the
remaining cap covers its worst case (dry-run: 1 reached / 2 attempts; C: 2 reached / 3 attempts);
the launcher counts every attempt before sending and refuses beyond the cell allowance.

usage: own78a_harness.py --block <name> --cells A0,A1,... --repo <worktree> --trees <dir>
         --driver <bin> --driver-sha256 <sha256> --out <dir> --budget-file <json> [--stub]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "own78a_launcher.py"
EXAMPLES_REL = "libs/cua-driver/examples/jev-use"
LANE_CAP_REACHED = 24
LANE_CAP_ATTEMPTS = 30
CELL_WORST = {"A0": (1, 2), "A1": (1, 2), "A2": (1, 2), "A3": (1, 2), "C": (2, 3)}  # (reached, attempts)
TREES = {  # arm -> (tree name, source SHA)
    "A0": ("pr", "039257811e0bbb2348c616c52562409923d2856f"),
    "A1": ("pr", "039257811e0bbb2348c616c52562409923d2856f"),
    "A2": ("f", None),  # F SHA passed with --f-sha
    "A3": ("pre", "2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4"),
    "C": ("f", None),
}
DUMMY_KEY = "own78a-dummy-key-not-a-secret"
MAX_CELLS_PER_BLOCK = 10
CELL_TIMEOUT_S = 180
FORBIDDEN_ENV = ("CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
                 "CUA_E2E_BROWSER_NO_SANDBOX", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE")
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


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def tree_matches(repo: Path, sha: str, tree_root: Path) -> dict:
    """Every tracked file of <sha>:<examples> exists in the export with the same blob id, and the
    export has no other file outside dependency/cache dirs."""
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", sha, "--", EXAMPLES_REL],
                             capture_output=True, text=True, check=True).stdout.splitlines()
    expected = {}
    for line in listing:
        meta, _, path = line.partition("\t")
        expected[path] = meta.split()[2]
    mismatched = [p for p, blob in expected.items()
                  if not (tree_root / p).is_file() or git_blob_sha(tree_root / p) != blob]
    skip = {".venv", "node_modules", "__pycache__"}
    extra = []
    for path in (tree_root / EXAMPLES_REL).rglob("*"):
        if path.is_file() and not (set(path.relative_to(tree_root).parts) & skip):
            rel = str(path.relative_to(tree_root))
            if rel not in expected:
                extra.append(rel)
    tree_id = subprocess.run(["git", "-C", str(repo), "rev-parse", f"{sha}:{EXAMPLES_REL}"],
                             capture_output=True, text=True, check=True).stdout.strip()
    return {"sha": sha, "examples_tree_id": tree_id, "files": len(expected),
            "mismatched": mismatched, "extra": extra, "ok": not mismatched and not extra}


def fixture_field_identity(examples: Path) -> dict:
    """The fixture's own field identity, read from its page source (target-owned)."""
    text = (examples / "fixture_server.py").read_text()
    match = re.search(r'<input name="([^"]+)"[^>]*aria-label="([^"]+)"', text)
    button = re.search(r'<button type="submit">([^<]+)</button>', text)
    return {"input_name": match.group(1), "aria_label": match.group(2), "role": "textbox",
            "submit_text": button.group(1) if button else None}


def make_server(examples: Path, *, token: str):
    sys.path.insert(0, str(examples))
    import fixture_server
    from fixture_server import FixtureHandler, FixtureServer

    page = fixture_server.PAGE.replace(b"</form>", b"</form>" + JOURNAL_SCRIPT)
    assert page != fixture_server.PAGE

    class CountingHandler(FixtureHandler):
        def do_GET(self) -> None:  # noqa: N802
            srv = self.server
            with srv.lock:
                srv.counts[f"GET {self.path}"] = srv.counts.get(f"GET {self.path}", 0) + 1
            if self.path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", page)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            srv = self.server
            with srv.lock:
                srv.counts[f"POST {self.path}"] = srv.counts.get(f"POST {self.path}", 0) + 1
            if self.path == "/event/input":
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length).decode() or "{}")
                except ValueError:
                    body = {}
                value = body.get("value") if isinstance(body.get("value"), str) else ""
                entry = {"seq": body.get("seq") if isinstance(body.get("seq"), int) else None,
                         "arrival_ns": now(), "length": len(value), "equals_token": value == token,
                         "trusted": body.get("trusted") if isinstance(body.get("trusted"), bool) else None,
                         "input_type": body.get("input_type") if isinstance(body.get("input_type"), str) else None}
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


def _paths(value, prefix="", depth=0):
    if isinstance(value, str) and value[:1] == "{" and depth > 0:
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, dict) or depth >= 3:
        return []
    out = []
    for key, item in value.items():
        out.append(prefix + key)
        out.extend(_paths(item, prefix + key + ".", depth + 1))
    return out


class StubServer:
    """Loopback stand-in speaking the TypeSafe /v1/systemone wire format (smoke only).

    Records only question names, criteria ids, state key paths, the chosen id and whether an
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
                answers = {}
                record = {"arrival_ns": now(), "auth_header_present": bool(self.headers.get("Authorization")),
                          "state_key_paths": _paths(body.get("state")), "questions": {}}
                for name, question in questions.items():
                    criteria = list((question or {}).get("criteria") or {})
                    choice = next((c for c in ("type-verification-value", "submit-form") if c in criteria), "abstain")
                    rest = [c for c in criteria if c != choice]
                    probabilities = {c: (0.9 if c == choice else round(0.1 / len(rest), 6)) for c in criteria}
                    answers[name] = {"type": "choice", "choice": choice, "confidence": 0.9, "probabilities": probabilities}
                    record["questions"][name] = {"criteria_ids": criteria, "chosen": choice}
                with stub.lock:
                    record["n"] = len(stub.log) + 1
                    stub.log.append(record)
                payload = json.dumps({"model": "own78a-loopback-stub", "usage": {"input_tokens": 0, "output_tokens": 0},
                                      "answers": answers}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("x-typesafe-request-id", f"own78a-stub-{record['n']}")
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
        self.data = (json.loads(path.read_text()) if path.exists() else
                     {"lane_cap_reached": LANE_CAP_REACHED, "lane_cap_attempts": LANE_CAP_ATTEMPTS,
                      "attempts": 0, "reached": 0, "guard_refused": 0, "by_cell": {}})

    def remaining(self) -> tuple[int, int]:
        return LANE_CAP_REACHED - self.data["reached"], LANE_CAP_ATTEMPTS - self.data["attempts"]

    def can_start(self, arm: str) -> bool:
        reached, attempts = self.remaining()
        need_r, need_a = CELL_WORST[arm]
        return reached >= need_r and attempts >= need_a

    def add(self, cell_id: str, attempts: int, reached: int, refused: int) -> None:
        self.data["attempts"] += attempts
        self.data["reached"] += reached
        self.data["guard_refused"] += refused
        self.data["by_cell"][cell_id] = {"attempts": attempts, "reached": reached, "guard_refused": refused}
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")


def session_pids(xdg_runtime: str) -> dict[int, str]:
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


def run_cell(args, out: Path, budget: Budget, *, index: int, arm: str) -> dict:
    cell_id = f"{args.block}-{index:02d}-{arm}"
    token = f"own78a-{args.block}-{index:02d}-{arm.lower()}"
    tree_name, _ = TREES[arm]
    examples = args.trees / tree_name / EXAMPLES_REL
    cdir = out / "cells" / cell_id
    cdir.mkdir(parents=True, exist_ok=False)
    log_path, receipts_path = cdir / "runner.jsonl", cdir / "receipts.jsonl"
    server = make_server(args.fixture_examples, token=token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    dry = arm != "C"
    provider = "live" if arm == "A3" else "typesafe"
    flags = ["--provider", provider, "--fixture-url", url, "--token", token, "--log", str(log_path)]
    flags += ["--dry-run", "--max-steps", "1"] if dry else ["--max-steps", "2"]
    cmd = [str(examples / ".venv/bin/python"), str(LAUNCHER), str(examples), *flags]
    env = dict(os.environ)
    env.pop("TYPESAFE_BASE_URL", None)
    for name in [k for k in env if k.startswith("CUA_S1_")]:
        env.pop(name)
    env.update({"CUA_DRIVER_BIN": str(args.driver), "OWN78A_RECEIPT_LOG": str(receipts_path),
                "OWN78A_TRIAL": cell_id})
    if arm == "A1":
        env["OWN78A_SEAM_ADD_FORM"] = "1"
    if dry:
        env["OWN78A_FORBID_MUTATION"] = "1"
    stub = None
    if args.stub:
        stub = StubServer()
        env["TYPESAFE_BASE_URL"] = stub.url
        env["TYPESAFE_API_KEY"] = DUMMY_KEY
        env["OWN78A_ATTEMPT_ALLOWANCE"] = "0"
        env["OWN78A_REACH_ALLOWANCE"] = "0"
    else:
        reached_left, attempts_left = budget.remaining()
        need_r, need_a = CELL_WORST[arm]
        env["OWN78A_REACH_ALLOWANCE"] = str(min(need_r, reached_left))
        env["OWN78A_ATTEMPT_ALLOWANCE"] = str(min(need_a, attempts_left))
    xdg = os.environ["XDG_RUNTIME_DIR"]
    before = session_pids(xdg)
    cell = {"cell_id": cell_id, "block": args.block, "index": index, "arm": arm, "tree": tree_name,
            "source_sha": args.f_sha if tree_name == "f" else TREES[arm][1],
            "provider_flag": provider, "dry_run": dry, "max_steps": 1 if dry else 2,
            "fixture": "journal_variant", "token_sha256_16": hashlib.sha256(token.encode()).hexdigest()[:16],
            "stub": args.stub, "seam_add_form": arm == "A1", "forbid_mutation": dry,
            "loadavg_at_spawn": loadavg(),
            "key_in_runner_env": bool(env.get("TYPESAFE_API_KEY", "").strip()) and env.get("TYPESAFE_API_KEY") != DUMMY_KEY,
            "reach_allowance": int(env["OWN78A_REACH_ALLOWANCE"]),
            "attempt_allowance": int(env["OWN78A_ATTEMPT_ALLOWANCE"]),
            "utc_start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with (cdir / "stdout.txt").open("wb") as stdout_f, (cdir / "stderr.txt").open("wb") as stderr_f:
        proc = subprocess.Popen(cmd, cwd=examples, env=env, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
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
    time.sleep(0.6)  # let in-flight journal posts land before reading the oracle
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
    for pid, comm in leftovers.items():  # started by this cell inside this private session only
        if comm.startswith(("chrome", "cua-driver", "python", "node")):
            try:
                os.kill(pid, 9)
                killed.append(comm)
            except OSError:
                pass
    receipts = read_jsonl(receipts_path)
    http = [r for r in receipts if r.get("kind") == "http_attempt"]
    attempts = [r for r in http if not r.get("guard_refused") and not r.get("loopback")]
    reached = [r for r in attempts if isinstance(r.get("status"), int)]
    refused = [r for r in http if r.get("guard_refused")]
    submitted = (final_state or {}).get("submitted")
    cell.update({"rc": rc, "timed_out": timed_out, "submitted_is_none": submitted is None,
                 "submitted_equals_token": submitted == token, "server_counts": counts,
                 "submits": len(submit_ns), "input_events": len(journal_entries),
                 "loadavg_at_exit": loadavg(), "leftover_processes_killed": sorted(killed),
                 "http_attempts": len(attempts), "http_reached": len(reached), "guard_refused": len(refused),
                 "loopback_attempts": len([r for r in http if r.get("loopback")])})
    if not args.stub:
        budget.add(cell_id, len(attempts), len(reached), len(refused))
    (cdir / "cell.json").write_text(json.dumps(cell, indent=1, sort_keys=True) + "\n")
    with (cdir / "trial.jsonl").open("w", encoding="utf-8") as raw:
        raw.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        for event in read_jsonl(log_path):
            event.pop("token", None)
            raw.write(json.dumps({"type": "runner_event", "event": event}, sort_keys=True) + "\n")
        for receipt in receipts:
            raw.write(json.dumps({"type": "receipt", **receipt}, sort_keys=True) + "\n")
        for entry in journal_entries:
            raw.write(json.dumps({"type": "journal", **entry}, sort_keys=True) + "\n")
        for entry in stub_log:
            raw.write(json.dumps({"type": "stub", **entry}, sort_keys=True) + "\n")
    return cell


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", required=True)
    parser.add_argument("--cells", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--trees", type=Path, required=True)
    parser.add_argument("--f-sha", required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-file", type=Path, required=True)
    parser.add_argument("--stub", action="store_true")
    args = parser.parse_args()
    plan = [c for c in args.cells.split(",") if c]
    if len(plan) > MAX_CELLS_PER_BLOCK or any(c not in CELL_WORST for c in plan):
        print(json.dumps({"event": "refused", "reason": "bad plan or more than 10 cells"}))
        return 4
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        print(json.dumps({"event": "refused", "reason": "not inside the isolated X11 session"}))
        return 97
    args.out.mkdir(parents=True, exist_ok=False)
    args.fixture_examples = args.trees / "f" / EXAMPLES_REL
    trees = {name: tree_matches(args.repo, sha, args.trees / name)
             for name, sha in (("pr", TREES["A0"][1]), ("f", args.f_sha), ("pre", TREES["A3"][1]))}
    driver_version = subprocess.run([str(args.driver), "--version"], capture_output=True, text=True).stdout.strip()
    check = {"block": args.block, "plan": plan, "stub": args.stub, "trees": trees,
             "driver_sha256": sha256_file(args.driver), "driver_sha256_expected": args.driver_sha256,
             "driver_version_in_session": driver_version,
             "forbidden_env_present": [n for n in FORBIDDEN_ENV if n in os.environ],
             "display_set": bool(os.environ.get("DISPLAY")),
             "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
             "typesafe_base_url_preset": "TYPESAFE_BASE_URL" in os.environ,
             "launcher_sha256": sha256_file(LAUNCHER), "harness_sha256": sha256_file(Path(__file__)),
             "fixture_field": fixture_field_identity(args.fixture_examples),
             "python": sys.version.split()[0], "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "loadavg_at_start": loadavg()}
    check["ok"] = (all(t["ok"] for t in trees.values()) and check["driver_sha256"] == args.driver_sha256
                   and not check["forbidden_env_present"] and check["display_set"]
                   and not check["typesafe_base_url_preset"])
    (args.out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "key_present": check["typesafe_key_present"],
                      "driver_version": driver_version}), flush=True)
    if not check["ok"]:
        return 2
    if not args.stub and not check["typesafe_key_present"]:
        print(json.dumps({"event": "blocked", "reason": "TYPESAFE_API_KEY absent in session"}), flush=True)
        return 3
    budget = Budget(args.budget_file)
    stopped = None
    with (args.out / "cells.jsonl").open("a", encoding="utf-8") as cells_log:
        for index, arm in enumerate(plan, start=1):
            if not args.stub and not budget.can_start(arm):
                stopped = f"lane cap: {budget.data['reached']} reached / {budget.data['attempts']} attempts used"
                break
            try:
                cell = run_cell(args, args.out, budget, index=index, arm=arm)
            except Exception as error:  # a broken cell is data
                cell = {"cell_id": f"{args.block}-{index:02d}-{arm}", "block": args.block, "arm": arm,
                        "harness_error": f"{type(error).__name__}: {error}"}
            cells_log.write(json.dumps(cell, sort_keys=True) + "\n")
            cells_log.flush()
            print(json.dumps({"event": "cell", "id": cell["cell_id"], "rc": cell.get("rc"),
                              "submitted_is_none": cell.get("submitted_is_none"),
                              "verified": cell.get("submitted_equals_token"), "inputs": cell.get("input_events"),
                              "submits": cell.get("submits"), "attempts": cell.get("http_attempts"),
                              "reached": cell.get("http_reached"), "lane_reached": budget.data["reached"],
                              "error": cell.get("harness_error")}, sort_keys=True), flush=True)
            time.sleep(0.3)
    (args.out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stopped_early": stopped,
        "lane_reached_after": budget.data["reached"], "lane_attempts_after": budget.data["attempts"],
        "loadavg_at_end": loadavg()}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
