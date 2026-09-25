#!/usr/bin/env python3
"""Fork-only provider-failure-after-typing evidence; no production modifications.

Reuses the earlier canonical bootstrap parser and byte-forwarding MCP auditor.
Adds an independent fixture input receipt and a fault on provider request two.
HTTP fixture replies are synthetic; this is not a live-model evaluation.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

CANDIDATE = "737cda114ae711713a3dbfa9c9ba76863dfd46b9"
MODEL = "owned-post-progress-fixture"
MODES = ("valid", "invalid-second", "http-error-second")
EXPECTED = ["type-verification-value", "submit-form"]
INPUT_TOOLS = frozenset({"browser_type", "browser_click", "click", "double_click",
    "right_click", "drag", "scroll", "type_text", "set_value", "press_key", "hotkey"})
AUDIT_SCRIPT = b'''<script>
// Test-only observer: never edits the field or invokes the agent.
const field = document.querySelector('input[name="value"]');
let sequence = 0;
for (const event of ['input', 'change']) {
  field.addEventListener(event, () => navigator.sendBeacon('/input-audit',
    JSON.stringify({sequence: ++sequence, event, value: field.value})));
}
</script>'''


@contextlib.contextmanager
def serving(server):
    with server:
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("owned server did not stop")


class InputReceipt:
    def __init__(self):
        self.condition = threading.Condition()
        self.events = []

    def receive(self, value):
        if not isinstance(value, dict) or not isinstance(value.get("value"), str):
            raise ValueError("invalid input receipt")
        if value.get("event") not in ("input", "change"):
            raise ValueError("invalid event kind")
        if type(value.get("sequence")) is not int or value["sequence"] <= 0:
            raise ValueError("invalid input sequence")
        with self.condition:
            self.events.append({**value, "received_ns": time.monotonic_ns()})
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return list(self.events)

    def await_value(self, token):
        with self.condition:
            return self.condition.wait_for(
                lambda: any(event["value"] == token for event in self.events), timeout=2)


def audited_fixture(module):
    """Extend only the test fixture; the candidate page/form behavior is unchanged."""
    receipt = InputReceipt()

    class Handler(module.FixtureHandler):
        def do_GET(self):
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", module.PAGE + AUDIT_SCRIPT)
            else:
                super().do_GET()

        def do_POST(self):
            if self.path == "/input-audit":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16384:
                        raise ValueError("input receipt too large or absent")
                    receipt.receive(json.loads(self.rfile.read(length)))
                    self._send(200, "application/json", b"{}")
                except (ValueError, TypeError):
                    self._send(400, "application/json", b"{}")
            else:
                super().do_POST()

    server = module.FixtureServer(("127.0.0.1", 0))
    server.RequestHandlerClass = Handler
    return server, receipt


def provider_reply(payload, index, mode):
    if mode not in MODES or index not in (0, 1):
        raise ValueError("unexpected mode or extra provider call")
    if payload.get("model") != MODEL:
        raise ValueError("model selection was not preserved")
    question = payload.get("questions", {}).get("candidate", {})
    criteria = question.get("criteria")
    if question.get("type") != "choice" or not isinstance(criteria, dict):
        raise ValueError("invalid candidate question")
    intended = EXPECTED[index]
    if intended not in criteria:
        raise ValueError("expected next action is not a current candidate")
    if index == 1 and mode == "http-error-second":
        return 503, {"error": "owned fixture unavailable"}, None
    choice = "not-a-supplied-candidate" if index == 1 and mode == "invalid-second" else intended
    if choice != intended and choice in criteria:
        raise ValueError("invalid choice unexpectedly supplied")
    return 200, {"model": MODEL, "answers": {"candidate": {
        "type": "choice", "choice": choice, "confidence": 1.0,
        "probabilities": {key: float(key == intended) for key in criteria},
    }}}, choice


class Responder(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, mode, receipt, token):
        self.mode, self.receipt, self.token = mode, receipt, token
        self.requests, self.errors = [], []
        self.lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), ProviderHandler)


class ProviderHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if self.path != "/v1/systemone" or self.headers.get("Authorization"):
                raise ValueError("unexpected route or credentials")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length))
            with self.server.lock:
                index = len(self.server.requests)
                typed = index == 1 and self.server.receipt.await_value(self.server.token)
                if index == 1 and not typed:
                    raise ValueError("no independent completed-typing receipt before fault")
                status, result, choice = provider_reply(payload, index, self.server.mode)
                self.server.requests.append({"request_index": index + 1, "status": status,
                    "choice": choice, "typing_observed_before_response": typed,
                    "response_ns": time.monotonic_ns()})
        except Exception as error:
            self.server.errors.append(f"{type(error).__name__}: {error}")
            status, result = 400, {"error": "fixture rejected request"}
        raw = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


def validate_case(mode, code, events, calls, observed, token, requests, inputs, errors):
    assert mode in MODES and not errors, errors
    assert len(requests) == 2 and requests[1]["typing_observed_before_response"] is True, requests
    assert [r["request_index"] for r in requests] == [1, 2]
    assert requests[0]["choice"] == EXPECTED[0] and requests[0]["status"] == 200
    assert any(e["value"] == token and e["received_ns"] <= requests[1]["response_ns"] for e in inputs), inputs
    steps = [e for e in events if e.get("event") == "step"]
    actions = [e.get("candidate") for e in steps]
    assert all(e.get("dry_run") is False for e in steps)
    names = [c["tool"] for c in calls]
    allowed = INPUT_TOOLS | {"browser_prepare", "list_windows", "get_browser_state",
                             "browser_navigate", "get_window_state", "parse_visual_regions"}
    assert all(name in allowed for name in names), names
    assert names.count("browser_navigate") == 1, names
    mutations = [name for name in names if name in INPUT_TOOLS]
    if mode == "valid":
        assert code == 0 and actions == EXPECTED, (code, actions)
        assert mutations == ["browser_type", "browser_click"], mutations
        assert requests[1]["status"] == 200 and requests[1]["choice"] == EXPECTED[1]
        assert observed == {"submitted": token}, observed
        assert events[-1] == {"event": "outcome", "outcome": "verified", "token": token}
    else:
        assert code == 1 and actions == [EXPECTED[0]], (code, actions)
        assert mutations == ["browser_type"], mutations
        assert observed == {"submitted": None}, observed
        assert events[-1].get("outcome") == "abstained", events
        assert events[-1].get("reason") == ("invalid_response" if mode == "invalid-second" else "http_error")
        assert requests[1]["status"] == (200 if mode == "invalid-second" else 503)
    return {"case_passed": True, "provider_requests": 2, "actions": actions,
            "mutation_calls": mutations, "typing_independently_observed": True,
            "final_fixture_state": observed}


def exercise(root, out, driver):
    import jev_wave1_http  # Reuse its unchanged byte-forwarding auditor.
    base = root / "libs/cua-driver/examples/jev-use"
    sys.path.insert(0, str(base))
    import fixture_server
    out.mkdir(parents=True, exist_ok=False)
    summary = {"complete": False, "candidate_sha": CANDIDATE, "cases": []}
    env = {k: v for k, v in os.environ.items() if not k.startswith(("JEV_", "TYPESAFE_", "OPENJEV_"))}
    env.update(JEV_API_KEY="", TYPESAFE_API_KEY="")
    try:
        for language in ("python", "typescript"):
            for mode in MODES:
                start = time.monotonic()
                case = out / f"{language}-{mode}"
                case.mkdir()
                token = f"post-progress-{language}-{mode}"
                record = {"language": language, "mode": mode, "case_passed": False}
                summary["cases"].append(record)
                fixture, receipt = audited_fixture(fixture_server)
                responder = Responder(mode, receipt, token)
                with serving(fixture) as fixture_url, serving(responder) as provider_url:
                    audit, log = case / "mcp-tools.jsonl", case / "runner.jsonl"
                    audit.touch()
                    wrapper = case / "driver-with-audit"
                    exports = [f"export {key}={shlex.quote(env[key])}" for key in
                        ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "CUA_DRIVER_PERMISSION_MODE",
                         "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS", "CUA_E2E_BROWSER_NO_SANDBOX",
                         "CUA_E2E_BROWSER_STDERR") if key in env]
                    wrapper.write_text("#!/bin/bash\nset -euo pipefail\n" + "\n".join(exports) + "\nexec " +
                        shlex.join([sys.executable, str(Path(jev_wave1_http.__file__).resolve()), "proxy",
                                    str(driver), str(audit)]) + ' "$@"\n')
                    wrapper.chmod(0o700)
                    case_env = dict(env, CUA_DRIVER_BIN=str(wrapper))
                    command = ([sys.executable, "python/run.py"] if language == "python" else
                               ["node", "--import", "tsx", "typescript/run.ts"])
                    command += ["--provider", "local", "--jev-base-url", provider_url,
                        "--jev-model", MODEL, "--fixture-url", fixture_url + "/", "--token", token,
                        "--max-steps", "3", "--log", str(log)]
                    ran = subprocess.run(command, cwd=base, env=case_env, text=True,
                                         capture_output=True, timeout=180)
                    (case / "runner.log").write_text(ran.stdout + ran.stderr)
                    events = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
                    calls = [json.loads(line) for line in audit.read_text().splitlines()]
                    with urlopen(fixture_url + "/state", timeout=2) as response:
                        observed = json.load(response)
                    inputs = receipt.snapshot()
                    for filename, value in (("http-requests.json", responder.requests),
                        ("input-receipts.json", inputs), ("fixture-state.json", observed),
                        ("fixture-errors.json", responder.errors)):
                        (case / filename).write_text(json.dumps(value, indent=2) + "\n")
                    record.update(validate_case(mode, ran.returncode, events, calls, observed,
                                                token, responder.requests, inputs, responder.errors))
                record["elapsed_through_fixture_cleanup_seconds"] = round(time.monotonic() - start, 3)
        summary["complete"] = True
    finally:
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def bootstrap(root, out, workflow_sha):
    from run_canonical_jev_browser import recipe, git, CANONICAL_BLOB
    out.mkdir(parents=True, exist_ok=False)
    result = {"candidate_sha": CANDIDATE, "workflow_sha": workflow_sha,
              "canonical_recipe_blob": CANONICAL_BLOB, "stages": [], "complete": False}
    try:
        assert git(root, "rev-parse", "HEAD") == CANDIDATE
        assert not git(root, "status", "--porcelain")
        workflow, canonical = recipe(root)
        env = dict(os.environ)
        assert env.get("RUNNER_TEMP"), "requires disposable hosted runner"
        for key, value in workflow["jobs"]["mock-e2e-linux"]["env"].items():
            env[key] = str(value).replace("${{ github.workspace }}", str(root))
        env.update(JEV_API_KEY="", TYPESAFE_API_KEY="", PYTHONUNBUFFERED="1")
        default_dir = workflow["defaults"]["run"]["working-directory"]
        command = shlex.join(["uv", "run", "--frozen", "python", str(Path(__file__).resolve()),
            "exercise", "--candidate-dir", str(root), "--evidence-dir", str(out / "http-proof"),
            "--driver", env["CUA_DRIVER_BIN"]])
        session = out / "x11-session.sh"
        session.write_text('set -euo pipefail\nopenbox >"$RUNNER_TEMP/post-progress-openbox.log" 2>&1 &\nwm=$!\n'
            'picom --backend xrender --config /dev/null >"$RUNNER_TEMP/post-progress-picom.log" 2>&1 &\ncompositor=$!\n'
            'trap \'kill "$wm" "$compositor" 2>/dev/null || true\' EXIT\nsleep 2\n' +
            f"cd {shlex.quote(str(root / default_dir))}\n{command}\n")
        stages = list(canonical[:4]) + [{"name": "HTTP failures after confirmed fixture typing",
            "run": shlex.join(["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24",
                                  "dbus-run-session", "--", "bash", str(session)])}]
        for index, step in enumerate(stages, 1):
            stage_start = time.monotonic()
            script = out / f"stage-{index:02d}.sh"
            script.write_text(step["run"] + "\n")
            directory = str(step.get("working-directory", default_dir)).replace("${{ github.workspace }}", str(root))
            cwd = Path(directory) if Path(directory).is_absolute() else root / directory
            assert cwd.resolve().is_relative_to(root.resolve())
            with (out / f"stage-{index:02d}.log").open("w") as log:
                run = subprocess.run(["bash", "-e", str(script)], cwd=cwd, env=env,
                                     stdout=log, stderr=subprocess.STDOUT, timeout=2100)
            result["stages"].append({"name": step["name"], "exit_code": run.returncode,
                                    "elapsed_seconds": round(time.monotonic() - stage_start, 3)})
            print(json.dumps(result["stages"][-1]), flush=True)
            if run.returncode:
                break
        result["tracked_candidate_source_unchanged"] = not git(root, "diff", "--name-only", "HEAD")
        result["driver_sha256"] = hashlib.sha256(Path(env["CUA_DRIVER_BIN"]).read_bytes()).hexdigest()
        proof = out / "http-proof/summary.json"
        result["complete"] = (len(result["stages"]) == 5 and
            all(s["exit_code"] == 0 for s in result["stages"]) and proof.exists() and
            json.loads(proof.read_text())["complete"] and result["tracked_candidate_source_unchanged"])
    finally:
        result["controller_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
        (out / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n" for p in files))
    return 0 if result["complete"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("exercise", "bootstrap"))
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--workflow-sha", default="")
    args = parser.parse_args()
    root, out = args.candidate_dir.resolve(), args.evidence_dir.resolve()
    if args.command == "bootstrap":
        return bootstrap(root, out, args.workflow_sha)
    assert args.driver
    exercise(root, out, args.driver.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
